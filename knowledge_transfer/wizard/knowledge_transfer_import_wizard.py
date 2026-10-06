import base64
import binascii
import io
import json
import posixpath
import re
import zipfile

from odoo import api, fields, models, release
from odoo.exceptions import UserError

from ..models.knowledge_transfer_mixin import (
    CONTAINER_NAME, MANIFEST_NAME, MAX_UNCOMPRESSED_SIZE, MAX_ZIP_FILES,
    SUPPORTED_FORMAT_VERSIONS,
)
from ..tools.body_rewriter import BodyResolver, BodyRewriter

_RE_KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ImportResolver(BodyResolver):
    """Turn ZIP markers into the ids of the records created by the import."""

    def __init__(self, importer):
        super().__init__()
        self.importer = importer

    def article(self, ref):
        if not isinstance(ref, str):
            return None  # a raw id of the source database is never trusted
        article = self.importer.article_by_key.get(ref)
        return article.id if article else None

    def article_url(self, token, fragment):
        return f"/knowledge/article/{token}{fragment}"

    def attachment(self, ref):
        if not isinstance(ref, str) or not ref.isdigit():
            return None
        return self.importer.get_attachment(int(ref), self.article_key)

    def attachment_id(self, token):
        return token.id

    def attachment_url(self, token, kind, download):
        if kind == "image" and token.image_src:
            url = token.image_src
        else:
            url = f"/web/{'image' if kind == 'image' else 'content'}/{token.id}"
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}access_token={token.access_token}"
        return f"{url}&download=true" if download else url

    def attachment_file_data(self, token, file_data):
        file_data.update({
            "id": token.id,
            "access_token": token.access_token,
            "checksum": token.checksum,
            "url": token.url or "",
        })
        return file_data


class KnowledgeTransferImportWizard(models.TransientModel):
    _name = "knowledge.transfer.import.wizard"
    _inherit = ["knowledge.transfer.mixin"]
    _description = "Import Knowledge articles"

    zip_file = fields.Binary(string="ZIP file", attachment=False)
    zip_filename = fields.Char(string="ZIP file name")
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], default="draft", required=True)
    container_id = fields.Many2one("knowledge.article", string="Container article", readonly=True)
    article_count = fields.Integer(string="Articles created", readonly=True)
    attachment_count = fields.Integer(string="Attachments created", readonly=True)
    report = fields.Text(string="Warnings", readonly=True)

    @api.model
    def default_get(self, fields_list):
        self._check_transfer_access()
        return super().default_get(fields_list)

    @api.model_create_multi
    def create(self, vals_list):
        self._check_transfer_access()
        return super().create(vals_list)

    def action_import(self):
        self.ensure_one()
        self._check_transfer_access()
        if self.state != "draft":
            raise UserError(self.env._("This import has already been done."))
        if not self.zip_file:
            raise UserError(self.env._("Upload the ZIP file to import."))
        try:
            data = base64.b64decode(self.zip_file, validate=True)
        except (binascii.Error, ValueError):
            raise UserError(self.env._("The uploaded file is not a valid ZIP file."))
        package = self._read_package(data)
        # Everything is created inside one savepoint: if anything fails, none
        # of the records of this import survive.
        with self.env.cr.savepoint():
            importer = _PackageImporter(self, package)
            importer.run()
        self.write({
            "state": "done",
            "zip_file": False,
            "container_id": importer.container.id,
            "article_count": len(importer.created_articles),
            "attachment_count": importer.attachment_count,
            "report": "\n".join(importer.report_lines()),
        })
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Import"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_open_container(self):
        self.ensure_one()
        self._check_transfer_access()
        return self.container_id.action_home_page()

    @api.model
    def _get_or_create_container(self):
        """Return the current user's private root container article.

        Administrators can read every article (Knowledge's own system rule),
        so the search must explicitly target the user's own private roots.
        """
        Article = self.env["knowledge.article"]
        container = Article.search([
            ("parent_id", "=", False),
            ("name", "=", CONTAINER_NAME),
            ("category", "=", "private"),
            ("is_template", "=", False),
            ("article_member_ids.partner_id", "=", self.env.user.partner_id.id),
        ], order="id", limit=1)
        # article_create() is Knowledge's own helper for private articles:
        # internal_permission "none" plus the user as sole writing member.
        return container or Article.article_create(title=CONTAINER_NAME, is_private=True)

    # ------------------------------------------------------------------
    # Validation (nothing is created here)
    # ------------------------------------------------------------------

    def _read_package(self, data):
        """Validate the ZIP and return ``{"manifest": dict, "files": {path: bytes}}``.

        Raises a ``UserError`` on any problem, before anything is created.
        """
        _ = self.env._
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError):
            raise UserError(_("The uploaded file is not a valid ZIP file."))
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_FILES:
                raise UserError(_("The ZIP file contains too many files (maximum %s).", MAX_ZIP_FILES))
            if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_SIZE:
                raise UserError(_("The ZIP file is too large once uncompressed (maximum %s MB).",
                                  MAX_UNCOMPRESSED_SIZE // (1024 * 1024)))
            for info in infos:
                if not _is_safe_member(info):
                    raise UserError(_("The ZIP file contains a dangerous path: %s", info.filename))
            names = {info.filename for info in infos if not info.is_dir()}
            if MANIFEST_NAME not in names:
                raise UserError(_("The ZIP file has no %s: it was not created by the Knowledge export.",
                                  MANIFEST_NAME))
            files = {}
            total = 0
            try:
                for info in infos:
                    if info.is_dir():
                        continue
                    with archive.open(info) as member:
                        content = member.read(info.file_size + 1)
                    total += len(content)
                    if len(content) > info.file_size or total > MAX_UNCOMPRESSED_SIZE:
                        raise UserError(_("The ZIP file is too large once uncompressed (maximum %s MB).",
                                          MAX_UNCOMPRESSED_SIZE // (1024 * 1024)))
                    files[info.filename] = content
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, OSError):
                raise UserError(_("The uploaded file is not a valid ZIP file."))

        try:
            manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise UserError(_("The %s file of the ZIP is not valid JSON.", MANIFEST_NAME))
        if not isinstance(manifest, dict):
            raise UserError(_("The %s file of the ZIP is not valid.", MANIFEST_NAME))
        version = manifest.get("format_version")
        if isinstance(version, bool) or not isinstance(version, int) or version not in SUPPORTED_FORMAT_VERSIONS:
            raise UserError(_("Unsupported ZIP format version: %(version)s (supported: %(supported)s).",
                              version=version,
                              supported=", ".join(str(v) for v in sorted(SUPPORTED_FORMAT_VERSIONS))))
        self._validate_manifest(manifest, files)
        return {"manifest": manifest, "files": files}

    def _validate_manifest(self, manifest, files):
        _ = self.env._

        def invalid(reason):
            raise UserError(_("The %(file)s file of the ZIP is not valid: %(reason)s",
                              file=MANIFEST_NAME, reason=reason))

        articles = manifest.get("articles")
        attachments = manifest.get("attachments") or []
        if not isinstance(articles, list) or not articles:
            invalid(_("it contains no article."))
        if not isinstance(attachments, list):
            invalid(_("the attachment list is malformed."))
        indexes = set()
        for entry in attachments:
            if not isinstance(entry, dict) or not isinstance(entry.get("index"), int) or entry["index"] in indexes:
                invalid(_("an attachment entry is malformed."))
            indexes.add(entry["index"])
            if entry.get("type", "binary") == "binary":
                if entry.get("file") not in files:
                    invalid(_("the file of attachment %s is missing.", entry["index"]))
            elif not isinstance(entry.get("url"), str):
                invalid(_("the URL of attachment %s is missing.", entry["index"]))
        keys = set()
        for entry in articles:
            if not isinstance(entry, dict) or not _RE_KEY.match(str(entry.get("key") or "")):
                invalid(_("an article entry has no valid key."))
            if entry["key"] in keys:
                invalid(_("the article key %s is duplicated.", entry["key"]))
            parent_key = entry.get("parent_key")
            if parent_key is not None and parent_key not in keys:
                invalid(_("the parent of article %s must be listed before it.", entry["key"]))
            if entry.get("body") not in files:
                invalid(_("the body of article %s is missing.", entry["key"]))
            if not isinstance(entry.get("name", ""), str) or not isinstance(entry.get("icon") or "", str):
                invalid(_("the name or icon of article %s is malformed.", entry["key"]))
            cover = entry.get("cover")
            if cover and (not isinstance(cover, dict) or cover.get("attachment") not in indexes):
                invalid(_("the cover of article %s is missing.", entry["key"]))
            if not isinstance(entry.get("properties_definition") or [], list) \
                    or not isinstance(entry.get("properties") or {}, dict) \
                    or not isinstance(entry.get("stages") or [], list):
                invalid(_("the item data of article %s is malformed.", entry["key"]))
            keys.add(entry["key"])


class _PackageImporter:
    """Create the articles and attachments of a validated package."""

    def __init__(self, wizard, package):
        self.wizard = wizard
        self.env = wizard.env
        self.manifest = package["manifest"]
        self.files = package["files"]
        self.attachment_entries = {entry["index"]: entry for entry in self.manifest.get("attachments") or []}
        self.article_by_key = {}
        self.created_articles = self.env["knowledge.article"]
        self.created_attachments = {}
        self.attachment_count = 0
        self.container = self.env["knowledge.article"]
        self.warnings = []

    def run(self):
        Article = self.env["knowledge.article"]
        self.warnings = [w for w in self.manifest.get("warnings") or [] if isinstance(w, dict)]
        source_series = self.manifest.get("odoo_series")
        if source_series != release.serie:
            self.warnings.append({"article_key": None, "code": "series_mismatch", "detail": str(source_series)})

        self.container = self.wizard._get_or_create_container()
        now = fields.Datetime.context_timestamp(self.wizard, fields.Datetime.now())
        suffix = now.strftime("%Y-%m-%d %H:%M")

        stage_by_key = {}
        sibling_counter = {}
        for entry in self.manifest["articles"]:
            parent = self.article_by_key.get(entry.get("parent_key")) or self.container
            is_root = not entry.get("parent_key")
            name = entry.get("name") or ""
            vals = {
                "name": f"{name} - {suffix}" if is_root else name,
                "icon": entry.get("icon") or False,
                "full_width": bool(entry.get("full_width")),
                "parent_id": parent.id,
                "body": "<p><br></p>",
                "article_properties_definition": entry.get("properties_definition") or False,
            }
            if not is_root:
                sibling_counter[parent.id] = sibling_counter.get(parent.id, 0) + 1
                vals["sequence"] = sibling_counter[parent.id]
                if entry.get("is_article_item"):
                    vals["is_article_item"] = True
                    if entry.get("stage_key") in stage_by_key:
                        vals["stage_id"] = stage_by_key[entry["stage_key"]].id
                    if entry.get("properties"):
                        vals["article_properties"] = entry["properties"]
            article = Article.create(vals)
            self.article_by_key[entry["key"]] = article
            self.created_articles |= article
            for stage in entry.get("stages") or []:
                stage_by_key[stage.get("key")] = self.env["knowledge.article.stage"].create({
                    "name": stage.get("name") or "",
                    "sequence": stage.get("sequence") or 0,
                    "fold": bool(stage.get("fold")),
                    "parent_id": article.id,
                })

        resolver = ImportResolver(self)
        rewriter = BodyRewriter(resolver, (), self.wizard._get_neutral_texts())
        for entry in self.manifest["articles"]:
            article = self.article_by_key[entry["key"]]
            try:
                raw_body = self.files[entry["body"]].decode("utf-8")
            except UnicodeDecodeError:
                raise UserError(self.env._("The body of article %s is not valid UTF-8.", entry["key"]))
            values = {"body": rewriter.rewrite(raw_body, entry["key"])}
            cover = entry.get("cover")
            if cover:
                values.update(self._create_cover(cover, article))
            article.write(values)
        self.warnings.extend(resolver.warnings)

    def get_attachment(self, index, article_key):
        """Create (once) the attachment shipped under ``index``."""
        if index in self.created_attachments:
            return self.created_attachments[index]
        entry = self.attachment_entries.get(index)
        if not entry:
            self.created_attachments[index] = None
            return None
        owner = self.article_by_key.get(entry.get("article_key")) or self.article_by_key.get(article_key)
        attachment = self._create_attachment(entry, "knowledge.article", owner.id if owner else 0)
        self.created_attachments[index] = attachment
        original_index = entry.get("original")
        if isinstance(original_index, int) and original_index != index:
            original = self.get_attachment(original_index, article_key)
            if original:
                attachment.original_id = original
        return attachment

    def _create_attachment(self, entry, res_model, res_id):
        vals = {
            "name": entry.get("name") or "attachment",
            "res_model": res_model,
            "res_id": res_id,
        }
        if entry.get("mimetype"):
            vals["mimetype"] = entry["mimetype"]
        if entry.get("type", "binary") == "binary":
            vals["raw"] = self.files[entry["file"]]
        else:
            vals.update({"type": "url", "url": entry["url"]})
        attachment = self.env["ir.attachment"].create(vals)
        attachment.generate_access_token()
        self.attachment_count += 1
        return attachment

    def _create_cover(self, cover, article):
        entry = self.attachment_entries[cover["attachment"]]
        # Uploaded covers are created unlinked; knowledge.cover links them.
        attachment = self._create_attachment(entry, "knowledge.cover", 0)
        knowledge_cover = self.env["knowledge.cover"].create({"attachment_id": attachment.id})
        position = cover.get("position")
        return {
            "cover_image_id": knowledge_cover.id,
            "cover_image_position": position if isinstance(position, (int, float)) else 0,
        }

    def report_lines(self):
        names = {}
        for entry in self.manifest["articles"]:
            article = self.article_by_key.get(entry["key"])
            names[entry["key"]] = article.name if article else entry.get("name")
        return [self.wizard._format_transfer_warning(warning, names) for warning in self.warnings]


def _is_safe_member(info):
    """Reject absolute paths, parent traversal, drive letters and symlinks."""
    name = info.filename
    if not name or "\\" in name or "\x00" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return False
    normalized = posixpath.normpath(name)
    if normalized.startswith("../") or normalized == ".." or any(part == ".." for part in name.split("/")):
        return False
    is_symlink = (info.external_attr >> 16) & 0o170000 == 0o120000
    return not is_symlink
