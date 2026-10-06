import base64
import io
import json
import zipfile

from markupsafe import Markup
from PIL import Image

from odoo.tests import TransactionCase, new_test_user


def make_png(color="red"):
    buffer = io.BytesIO()
    Image.new("RGB", (20, 10), color).save(buffer, "PNG")
    return buffer.getvalue()


def make_zip(files):
    """Build a ZIP from ``{path: bytes|str|dict}`` (dicts are dumped as JSON)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in files.items():
            if isinstance(content, dict):
                content = json.dumps(content)
            archive.writestr(path, content)
    return buffer.getvalue()


class KnowledgeTransferCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env, login="kt_admin", groups="base.group_user,base.group_system",
            tz="America/Argentina/Buenos_Aires")
        cls.other_admin = new_test_user(
            cls.env, login="kt_admin_2", groups="base.group_user,base.group_system")
        cls.internal_user = new_test_user(cls.env, login="kt_user", groups="base.group_user")
        cls.env = cls.env(user=cls.admin)
        cls.Article = cls.env["knowledge.article"]

        # Tree: root > (child_a, child_b > grandchild); plus an outside article.
        cls.outside = cls.Article.article_create("Outside article")
        cls.root = cls.Article.article_create("Root article")
        cls.child_a = cls.Article.create({"name": "Child A", "parent_id": cls.root.id, "sequence": 1})
        cls.child_b = cls.Article.create({"name": "Child B", "parent_id": cls.root.id, "sequence": 2})
        cls.grandchild = cls.Article.create({"name": "Grandchild", "parent_id": cls.child_b.id})
        cls.image = cls.env["ir.attachment"].create({
            "name": "picture.png",
            "raw": make_png(),
            "res_model": "knowledge.article",
            "res_id": cls.child_a.id,
        })
        cls.image.generate_access_token()
        cls.child_a.body = Markup(
            '<h1>Child A</h1>'
            '<p><img src="%s?access_token=%s" data-attachment-id="%s" alt="Picture"></p>'
            '<p><a class="o_knowledge_article_link" href="/knowledge/article/%s" data-res_id="%s">'
            'Grandchild</a></p>'
            '<p><a class="o_knowledge_article_link" href="/knowledge/article/%s" data-res_id="%s">'
            'Outside article</a></p>'
        ) % (cls.image.image_src, cls.image.access_token, cls.image.id,
             cls.grandchild.id, cls.grandchild.id, cls.outside.id, cls.outside.id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def export_zip(self, articles, user=None):
        Wizard = self.env["knowledge.transfer.export.wizard"]
        if user:
            Wizard = Wizard.with_user(user)
        wizard = Wizard.create({"article_ids": [(6, 0, articles.ids)]})
        wizard.action_export()
        return base64.b64decode(wizard.zip_file)

    def read_zip(self, data):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        return json.loads(files["manifest.json"]), files

    def import_zip(self, data, user=None):
        Wizard = self.env["knowledge.transfer.import.wizard"]
        if user:
            Wizard = Wizard.with_user(user)
        wizard = Wizard.create({"zip_file": base64.b64encode(data), "zip_filename": "test.zip"})
        wizard.action_import()
        return wizard

    def snapshot(self):
        """State of every article and attachment, to prove nothing changed."""
        articles = self.env["knowledge.article"].sudo().with_context(active_test=False).search([])
        return {
            "articles": {
                article.id: (article.name, article.parent_id.id, article.sequence, article.body,
                             article.active, article.write_date, article.internal_permission)
                for article in articles
            },
            "attachments": self.env["ir.attachment"].sudo().search_count([]),
            "covers": self.env["knowledge.cover"].sudo().search_count([]),
        }

    def container_of(self, user):
        return self.env["knowledge.article"].sudo().search([
            ("parent_id", "=", False),
            ("name", "=", "Artículos importados Zinapsia"),
            ("article_member_ids.partner_id", "=", user.partner_id.id),
        ])
