import base64
import io
import json
import re
import zipfile
from datetime import datetime, timezone

from odoo import api, fields, models, release
from odoo.exceptions import AccessError, MissingError, UserError

from ..models.knowledge_transfer_mixin import FORMAT_VERSION, MANIFEST_NAME
from ..tools.body_rewriter import (
    ARTICLE_MARKER, ATTACHMENT_MARKER, BodyResolver, BodyRewriter,
)

RELATIONAL_PROPERTY_TYPES = {"many2one", "many2many"}


class ExportResolver(BodyResolver):
    """Turn real ids into ZIP markers, registering the attachments to ship."""

    def __init__(self, exporter):
        super().__init__()
        self.exporter = exporter

    def article(self, ref):
        if not isinstance(ref, int):
            return None
        key = self.exporter.key_by_article_id.get(ref)
        return f"{ARTICLE_MARKER}{key}" if key else None

    def article_url(self, token, fragment):
        return f"{token}{fragment}"

    def attachment(self, ref):
        if not isinstance(ref, int):
            return None
        return self.exporter.register_attachment(ref, self.article_key)

    def attachment_id(self, token):
        return f"{ATTACHMENT_MARKER}{token}"

    def attachment_url(self, token, kind, download):
        return f"{ATTACHMENT_MARKER}{token}:{kind}{'?download=true' if download else ''}"

    def attachment_file_data(self, token, file_data):
        file_data["id"] = f"{ATTACHMENT_MARKER}{token}"
        file_data.pop("access_token", None)
        return file_data


class KnowledgeTransferExportWizard(models.TransientModel):
    _name = "knowledge.transfer.export.wizard"
    _inherit = ["knowledge.transfer.mixin"]
    _description = "Export Knowledge articles"

    article_ids = fields.Many2many(
        "knowledge.article", string="Articles",
        domain="[('is_template', '=', False)]",
        help="Selected articles are exported together with all their sub-articles.")
    zip_file = fields.Binary(string="ZIP file", readonly=True, attachment=True)
    zip_filename = fields.Char(string="ZIP file name", readonly=True)

    @api.model
    def default_get(self, fields_list):
        self._check_transfer_access()
        return super().default_get(fields_list)

    @api.model_create_multi
    def create(self, vals_list):
        self._check_transfer_access()
        return super().create(vals_list)

    @api.model
    def action_open_with_articles(self, article_ids):
        """Open the wizard with articles preselected (list view "Action" menu)."""
        self._check_transfer_access()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Export"),
            "res_model": self._name,
            "view_mode": "form",
            "target": "new",
            "context": {"default_article_ids": [(6, 0, article_ids)]},
        }

    def action_export(self):
        self.ensure_one()
        self._check_transfer_access()
        if not self.article_ids:
            raise UserError(self.env._("Select at least one article to export."))
        content = self._build_zip()
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        self.write({
            "zip_file": base64.b64encode(content),
            "zip_filename": f"knowledge_export_{now.strftime('%Y%m%d_%H%M')}.zip",
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content?model={self._name}&id={self.id}&field=zip_file"
                   f"&filename_field=zip_filename&download=true",
            "target": "self",
        }

    # ------------------------------------------------------------------
    # Export logic
    # ------------------------------------------------------------------

    def _get_articles_to_export(self):
        """Return the exported articles, parents always before their children.

        Articles are read with the user's own rights (no sudo): the search
        only returns what the user can see. Archived/trashed articles and
        templates are skipped, together with everything below them.
        """
        Article = self.env["knowledge.article"]
        selected = self.article_ids.filtered(lambda a: a.active and not a.to_delete and not a.is_template)
        selected_ids = set(selected.ids)
        roots = selected.filtered(lambda a: not (a._get_ancestor_ids() & selected_ids))
        if not roots:
            return Article, Article
        candidates = Article.search([
            ("id", "child_of", roots.ids),
            ("is_template", "=", False),
            ("to_delete", "=", False),
        ])
        children_by_parent = {}
        for article in candidates:
            children_by_parent.setdefault(article.parent_id.id, Article)
            children_by_parent[article.parent_id.id] |= article

        ordered = Article

        def visit(article):
            nonlocal ordered
            ordered |= article
            children = children_by_parent.get(article.id, Article)
            for child in children.sorted(lambda c: (c.sequence, c.id)):
                visit(child)

        for root in roots.sorted(lambda r: (r.sequence, r.id)):
            visit(root)
        return roots, ordered

    def _build_zip(self):
        roots, articles = self._get_articles_to_export()
        if not articles:
            raise UserError(self.env._("None of the selected articles can be exported "
                                       "(they may be archived or in the trash)."))
        exporter = _ZipExporter(self, roots, articles)
        return exporter.build()


class _ZipExporter:
    """Accumulate articles, bodies and attachments, then write the ZIP."""

    def __init__(self, wizard, roots, articles):
        self.wizard = wizard
        self.env = wizard.env
        self.roots = roots
        self.articles = articles
        self.key_by_article_id = {article.id: f"a{index}" for index, article in enumerate(articles, start=1)}
        self.attachments = []  # manifest entries, index = position + 1
        self.attachment_index_by_id = {}
        self.attachment_payloads = {}
        self.stage_key_by_id = {}

    def register_attachment(self, attachment_id, article_key):
        """Ship an attachment the user can read; return its index or None."""
        if attachment_id in self.attachment_index_by_id:
            index = self.attachment_index_by_id[attachment_id]
            if index is not None and article_key:
                entry = self.attachments[index - 1]
                if article_key not in entry["articles"]:
                    entry["articles"].append(article_key)
            return index
        attachment = self.env["ir.attachment"].browse(attachment_id)
        try:
            if not attachment.exists():
                raise MissingError("missing")
            attachment.check_access("read")
            values = attachment.read(["name", "mimetype", "checksum", "type", "url", "original_id"])[0]
            payload = attachment.raw if values["type"] == "binary" else None
        except (AccessError, MissingError):
            self.attachment_index_by_id[attachment_id] = None
            return None
        if values["type"] == "binary" and not payload:
            self.attachment_index_by_id[attachment_id] = None
            return None

        index = len(self.attachments) + 1
        self.attachment_index_by_id[attachment_id] = index
        name = values["name"] or f"attachment_{index}"
        entry = {
            "index": index,
            "name": name,
            "mimetype": values["mimetype"],
            "checksum": values["checksum"],
            "type": values["type"],
            "article_key": article_key,
            "articles": [article_key] if article_key else [],
        }
        if values["type"] == "binary":
            entry["file"] = f"attachments/{index}__{_safe_filename(name)}"
            self.attachment_payloads[entry["file"]] = payload
        else:
            entry["url"] = values["url"]
        self.attachments.append(entry)
        if values["original_id"]:
            original_index = self.register_attachment(values["original_id"][0], article_key)
            if original_index:
                entry["original"] = original_index
        return index

    def build(self):
        manifest_articles = []
        bodies = {}
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        source_origins = [base_url.rstrip("/")] if base_url else []
        resolver = ExportResolver(self)
        rewriter = BodyRewriter(resolver, source_origins, self.wizard._get_neutral_texts())

        for article in self.articles:
            key = self.key_by_article_id[article.id]
            parent_key = self.key_by_article_id.get(article.parent_id.id) if article not in self.roots else None
            body_path = f"articles/{key}/body.html"
            bodies[body_path] = rewriter.rewrite(article.body, key)
            entry = {
                "key": key,
                "parent_key": parent_key,
                "sequence": article.sequence,
                "name": article.name or "",
                "icon": article.icon or "",
                "full_width": article.full_width,
                "is_article_item": article.is_article_item if parent_key else False,
                "body": body_path,
                "cover": None,
                "stage_key": None,
                "stages": [],
                "properties_definition": [],
                "properties": {},
            }
            if article.cover_image_id:
                resolver.article_key = key
                cover_index = self.register_attachment(article.cover_image_id.attachment_id.id, key)
                if cover_index:
                    entry["cover"] = {"attachment": cover_index, "position": article.cover_image_position}
                else:
                    resolver.warn("image_removed", self.wizard.env._("Cover"))
            self._export_items_data(article, entry, resolver)
            manifest_articles.append(entry)

        for entry in manifest_articles:
            entry["attachments"] = [a["index"] for a in self.attachments if entry["key"] in a["articles"]]

        manifest = {
            "format_version": FORMAT_VERSION,
            "odoo_series": release.serie,
            "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "articles": manifest_articles,
            "attachments": self.attachments,
            "warnings": resolver.warnings,
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))
            for path, body in bodies.items():
                archive.writestr(path, body)
            for path, payload in self.attachment_payloads.items():
                archive.writestr(path, payload)
        return buffer.getvalue()

    def _export_items_data(self, article, entry, resolver):
        """Stages, property definitions and item property values."""
        key = entry["key"]
        stages = self.env["knowledge.article.stage"].search([("parent_id", "=", article.id)])
        for stage in stages:
            self.stage_key_by_id[stage.id] = f"s{len(self.stage_key_by_id) + 1}"
        entry["stages"] = [{
            "key": self.stage_key_by_id[stage.id],
            "name": stage.name,
            "sequence": stage.sequence,
            "fold": stage.fold,
        } for stage in stages]
        definition = []
        for prop in article.article_properties_definition or []:
            prop = dict(prop)
            if prop.get("type") in RELATIONAL_PROPERTY_TYPES:
                prop.pop("default", None)
                prop.pop("domain", None)
            definition.append(prop)
        entry["properties_definition"] = definition

        if entry["is_article_item"]:
            entry["stage_key"] = self.stage_key_by_id.get(article.stage_id.id)
            values = {}
            for prop in article.read(["article_properties"])[0]["article_properties"] or []:
                value = prop.get("value")
                if value in (False, None, [], ""):
                    continue
                if prop.get("type") in RELATIONAL_PROPERTY_TYPES:
                    resolver.article_key = key
                    resolver.warn("property_value_removed", prop.get("string") or prop.get("name"))
                    continue
                values[prop["name"]] = value
            entry["properties"] = values


def _safe_filename(name):
    name = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE).strip("._") or "file"
    return name[:100]
