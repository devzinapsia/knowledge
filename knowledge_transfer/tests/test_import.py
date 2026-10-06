import json
import re
from unittest.mock import patch

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.knowledge_transfer.wizard.knowledge_transfer_import_wizard import _PackageImporter

from .common import KnowledgeTransferCase, make_zip

CONTAINER = "Artículos importados Zinapsia"


@tagged("post_install", "-at_install")
class TestKnowledgeTransferImport(KnowledgeTransferCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.zip_data = cls.export_zip(cls, cls.root)

    def _imported_root(self, wizard):
        return wizard.container_id.child_ids.sorted("id")[-1]

    def _assert_import_fails(self, data, message_part=None):
        """Use try/except, not assertRaises: assertRaises would roll back by
        itself and hide whether the import created anything."""
        before = self.snapshot()
        try:
            self.import_zip(data)
        except UserError as error:
            if message_part:
                self.assertIn(message_part, str(error))
        else:
            self.fail("The import should have failed.")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.container_of(self.admin))

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def test_import_creates_container_and_suffixed_root(self):
        self.assertFalse(self.container_of(self.admin))
        with freeze_time("2026-03-01 15:30:00"):
            wizard = self.import_zip(self.zip_data)
        container = wizard.container_id
        self.assertEqual(container, self.container_of(self.admin))
        self.assertEqual(container.name, CONTAINER)
        self.assertFalse(container.parent_id)
        self.assertEqual(container.category, "private")
        self.assertEqual(container.internal_permission, "none")
        self.assertEqual(container.article_member_ids.partner_id, self.admin.partner_id)
        # Buenos Aires is UTC-3.
        self.assertEqual(container.child_ids.name, "Root article - 2026-03-01 12:30")
        self.assertEqual(wizard.article_count, 4)
        self.assertEqual(wizard.attachment_count, 1)

    def test_import_reproduces_structure(self):
        wizard = self.import_zip(self.zip_data)
        root = self._imported_root(wizard)
        self.assertNotEqual(root, self.root)
        self.assertTrue(root.name.startswith("Root article - "))
        children = root.child_ids.sorted("sequence")
        self.assertEqual(children.mapped("name"), ["Child A", "Child B"])
        self.assertEqual(children[1].child_ids.mapped("name"), ["Grandchild"])
        self.assertTrue(all(article.category == "private" for article in root | children))

    def test_import_image_gets_new_attachment(self):
        wizard = self.import_zip(self.zip_data)
        child_a = self._imported_root(wizard).child_ids.filtered(lambda a: a.name == "Child A")
        new_image = self.env["ir.attachment"].search([
            ("res_model", "=", "knowledge.article"), ("res_id", "=", child_a.id)])
        self.assertEqual(len(new_image), 1)
        self.assertNotEqual(new_image, self.image)
        self.assertEqual(new_image.raw, self.image.raw)
        body = str(child_a.body)
        self.assertIn(f"/web/image/{new_image.id}-", body)
        self.assertIn(f"access_token={new_image.access_token}", body)
        self.assertIn(f'data-attachment-id="{new_image.id}"', body)
        self.assertNotIn(f"/web/image/{self.image.id}-", body)
        self.assertNotIn(self.image.access_token, body)
        self.assertNotIn("kt-attachment", body)

    def test_import_remaps_article_links(self):
        wizard = self.import_zip(self.zip_data)
        root = self._imported_root(wizard)
        child_a = root.child_ids.filtered(lambda a: a.name == "Child A")
        new_grandchild = root.child_ids.child_ids.filtered(lambda a: a.name == "Grandchild")
        body = str(child_a.body)
        self.assertIn(f'href="/knowledge/article/{new_grandchild.id}"', body)
        self.assertIn(f'data-res_id="{new_grandchild.id}"', body)
        self.assertNotIn(f"/knowledge/article/{self.grandchild.id}\"", body)

    def test_import_neutralizes_link_outside_zip(self):
        wizard = self.import_zip(self.zip_data)
        child_a = self._imported_root(wizard).child_ids.filtered(lambda a: a.name == "Child A")
        body = str(child_a.body)
        self.assertIn("Outside article", body)
        self.assertNotIn(f"/knowledge/article/{self.outside.id}", body)
        self.assertIn("Outside article", wizard.report)

    def test_import_neutralizes_raw_ids_in_zip(self):
        """A hand-made ZIP with raw ids of another database must not keep them."""
        manifest = {
            "format_version": 1, "odoo_series": "19.0",
            "articles": [{"key": "a1", "parent_key": None, "name": "Raw", "body": "articles/a1/body.html"}],
            "attachments": [],
        }
        body = (
            '<p><a href="/knowledge/article/%s">Foreign</a>'
            '<img src="/web/image/%s" alt="Foreign image"></p>'
        ) % (self.outside.id, self.image.id)
        wizard = self.import_zip(make_zip({"manifest.json": manifest, "articles/a1/body.html": body}))
        imported = self._imported_root(wizard)
        self.assertNotIn(f"/knowledge/article/{self.outside.id}", str(imported.body))
        self.assertNotIn(f"/web/image/{self.image.id}", str(imported.body))
        self.assertIn("Foreign", str(imported.body))
        self.assertTrue(wizard.report)

    def test_import_sanitizes_script(self):
        manifest = {
            "format_version": 1, "odoo_series": "19.0",
            "articles": [{"key": "a1", "parent_key": None, "name": "Script", "body": "articles/a1/body.html"}],
            "attachments": [],
        }
        body = '<p>Safe text</p><script>alert("x")</script><img src="x" onerror="alert(1)">'
        wizard = self.import_zip(make_zip({"manifest.json": manifest, "articles/a1/body.html": body}))
        imported_body = str(self._imported_root(wizard).body)
        self.assertIn("Safe text", imported_body)
        self.assertNotIn("<script", imported_body)
        self.assertNotIn("onerror", imported_body)

    def test_series_mismatch_is_a_warning(self):
        manifest = {
            "format_version": 1, "odoo_series": "17.0",
            "articles": [{"key": "a1", "parent_key": None, "name": "Old", "body": "articles/a1/body.html"}],
            "attachments": [],
        }
        wizard = self.import_zip(make_zip({"manifest.json": manifest, "articles/a1/body.html": "<p>x</p>"}))
        self.assertEqual(wizard.article_count, 1)
        self.assertIn("17.0", wizard.report)

    # ------------------------------------------------------------------
    # Container and existing data
    # ------------------------------------------------------------------

    def test_second_import_reuses_container(self):
        first = self.import_zip(self.zip_data)
        second = self.import_zip(self.zip_data)
        self.assertEqual(first.container_id, second.container_id)
        self.assertEqual(len(self.container_of(self.admin)), 1)
        roots = first.container_id.child_ids
        self.assertEqual(len(roots), 2)
        self.assertEqual(len(roots[0]._get_descendants()), 3)
        self.assertEqual(len(roots[1]._get_descendants()), 3)
        self.assertFalse(roots[0]._get_descendants() & roots[1]._get_descendants())

    def test_container_is_per_user(self):
        mine = self.import_zip(self.zip_data)
        theirs = self.import_zip(self.zip_data, user=self.other_admin)
        self.assertNotEqual(mine.container_id, theirs.container_id)
        self.assertEqual(theirs.container_id.article_member_ids.partner_id, self.other_admin.partner_id)

    def test_import_never_modifies_existing_articles(self):
        container = self.Article.article_create(title=CONTAINER, is_private=True)
        self.Article.create({"name": "Existing child", "parent_id": container.id})
        self.env.flush_all()
        before = self.snapshot()
        wizard = self.import_zip(self.zip_data)
        self.env.flush_all()
        self.assertEqual(wizard.container_id, container)
        after = self.snapshot()
        for article_id, state in before["articles"].items():
            self.assertEqual(after["articles"].get(article_id), state)

    # ------------------------------------------------------------------
    # Validation and transaction
    # ------------------------------------------------------------------

    def test_invalid_zip(self):
        self._assert_import_fails(b"this is not a zip file", "not a valid ZIP")

    def test_zip_without_manifest(self):
        self._assert_import_fails(make_zip({"articles/a1/body.html": "<p>x</p>"}), "manifest.json")

    def test_unsupported_format_version(self):
        manifest = {"format_version": 99, "articles": [], "attachments": []}
        self._assert_import_fails(make_zip({"manifest.json": manifest}), "Unsupported ZIP format version")

    def test_dangerous_path(self):
        manifest = {
            "format_version": 1,
            "articles": [{"key": "a1", "parent_key": None, "name": "x", "body": "articles/a1/body.html"}],
            "attachments": [],
        }
        for path in ("../evil.txt", "/etc/evil", "a/../../evil", "C:/evil"):
            with self.subTest(path=path):
                data = make_zip({"manifest.json": manifest, "articles/a1/body.html": "<p>x</p>", path: "x"})
                self._assert_import_fails(data, "dangerous path")

    def test_failure_mid_import_rolls_back_everything(self):
        before = self.snapshot()
        with patch.object(_PackageImporter, "get_attachment", side_effect=RuntimeError("boom")):
            try:
                self.import_zip(self.zip_data)
            except RuntimeError:
                pass
            else:
                self.fail("The simulated failure should have propagated.")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.container_of(self.admin))

    def test_round_trip_same_database(self):
        wizard = self.import_zip(self.zip_data)
        manifest_again, _files = self.read_zip(self.export_zip(self._imported_root(wizard)))
        manifest, _files = self.read_zip(self.zip_data)

        def shape(entries):
            names = {e["key"]: e["name"] for e in entries}
            return [(re.sub(r" - \d{4}-\d{2}-\d{2} \d{2}:\d{2}$", "", e["name"]),
                     names.get(e["parent_key"], "").split(" - ")[0] or None) for e in entries]

        self.assertEqual(shape(manifest_again["articles"]), shape(manifest["articles"]))
        self.assertEqual(len(manifest_again["attachments"]), len(manifest["attachments"]))
        self.assertEqual(json.dumps(sorted(a["checksum"] for a in manifest_again["attachments"])),
                         json.dumps(sorted(a["checksum"] for a in manifest["attachments"])))
