from odoo import api, models
from odoo.exceptions import AccessError

# Version of the ZIP layout written by the exporter. Bump it whenever the
# layout changes in a way older importers cannot read.
FORMAT_VERSION = 1
SUPPORTED_FORMAT_VERSIONS = {1}
MANIFEST_NAME = "manifest.json"

# Safety limits applied to an uploaded ZIP before anything is created.
MAX_ZIP_FILES = 5000
MAX_UNCOMPRESSED_SIZE = 500 * 1024 * 1024  # bytes

# Business data, not a UI string: the name of the per-user private article
# that receives every import. Kept in Spanish on purpose.
CONTAINER_NAME = "Artículos importados Zinapsia"

TRANSFER_GROUP = "base.group_system"


class KnowledgeTransferMixin(models.AbstractModel):
    _name = "knowledge.transfer.mixin"
    _description = "Knowledge transfer shared helpers"

    @api.model
    def _check_transfer_access(self):
        """Server-side guard: menus and ACLs are not the only protection."""
        if not self.env.su and not self.env.user.has_group(TRANSFER_GROUP):
            raise AccessError(self.env._("Only Knowledge administrators can transfer articles."))

    @api.model
    def _get_neutral_texts(self):
        """Visible placeholders left in a body where a reference was dropped."""
        _ = self.env._
        return {
            "image": lambda label: _("[Image not transferred: %s]", label),
            "file": lambda label: _("[File not transferred: %s]", label),
            "embedded": lambda label: _("[Embedded content not transferred: %s]", label),
        }

    @api.model
    def _format_transfer_warning(self, warning, article_names):
        _ = self.env._
        messages = {
            "article_link_removed": _("Link to an article that is not part of the export removed: \"%s\""),
            "attachment_link_removed": _("Link to a missing attachment removed: \"%s\""),
            "record_link_removed": _("Link to a record of the source database removed: \"%s\""),
            "image_removed": _("Image not available, removed: \"%s\""),
            "media_removed": _("Media source not available, removed: \"%s\""),
            "file_removed": _("File not available, removed: \"%s\""),
            "embedded_removed": _("Embedded component not transferred: \"%s\""),
            "view_filters_removed": _("Saved filters removed from the embedded view \"%s\""),
            "index_entry_removed": _("Article index entry not part of the export removed: \"%s\""),
            "property_value_removed": _("Relational property value cleared: \"%s\""),
            "series_mismatch": _("The ZIP was exported from Odoo %s, which differs from this database's version."),
        }
        template = messages.get(warning.get("code"), "%s")
        message = template % (warning.get("detail") or "")
        article_name = article_names.get(warning.get("article_key"))
        return f"{article_name}: {message}" if article_name else message
