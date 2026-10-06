import re

from odoo.tests import tagged

from .common import KnowledgeTransferCase


@tagged("post_install", "-at_install")
class TestKnowledgeTransferExport(KnowledgeTransferCase):

    def test_export_tree_manifest(self):
        manifest, files = self.read_zip(self.export_zip(self.root))
        self.assertEqual(manifest["format_version"], 1)
        self.assertTrue(manifest["odoo_series"])
        self.assertRegex(manifest["exported_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

        entries = manifest["articles"]
        self.assertEqual([e["name"] for e in entries], ["Root article", "Child A", "Child B", "Grandchild"])
        by_name = {e["name"]: e for e in entries}
        self.assertIsNone(by_name["Root article"]["parent_key"])
        self.assertEqual(by_name["Child A"]["parent_key"], by_name["Root article"]["key"])
        self.assertEqual(by_name["Child B"]["parent_key"], by_name["Root article"]["key"])
        self.assertEqual(by_name["Grandchild"]["parent_key"], by_name["Child B"]["key"])
        for entry in entries:
            # Keys are local to the ZIP, never database ids.
            self.assertRegex(entry["key"], r"^a\d+$")
            self.assertIn(entry["body"], files)
            self.assertEqual(entry["body"], f"articles/{entry['key']}/body.html")

    def test_export_parent_and_descendant_not_duplicated(self):
        manifest, _files = self.read_zip(self.export_zip(self.root | self.grandchild))
        names = [entry["name"] for entry in manifest["articles"]]
        self.assertEqual(names.count("Grandchild"), 1)
        self.assertEqual(len(names), 4)

    def test_export_skips_archived_articles(self):
        archived = self.Article.create({"name": "Archived child", "parent_id": self.root.id})
        self.Article.create({"name": "Below archived", "parent_id": archived.id})
        archived.action_archive()
        manifest, _files = self.read_zip(self.export_zip(self.root))
        names = [entry["name"] for entry in manifest["articles"]]
        self.assertNotIn("Archived child", names)
        self.assertNotIn("Below archived", names)

    def test_export_replaces_ids_by_markers(self):
        manifest, files = self.read_zip(self.export_zip(self.root))
        child_a = next(e for e in manifest["articles"] if e["name"] == "Child A")
        body = files[child_a["body"]].decode()
        self.assertNotIn(f"/web/image/{self.image.id}", body)
        self.assertNotIn(self.image.access_token, body)
        self.assertIn('src="kt-attachment:1:image"', body)
        self.assertIn("kt-article:", body)
        # The outside article is neutralized at export time: text kept, link dropped.
        self.assertIn("Outside article", body)
        self.assertNotIn(f"/knowledge/article/{self.outside.id}", body)
        self.assertFalse(re.search(r'data-res_id="\d+"', body))
        codes = [w["code"] for w in manifest["warnings"]]
        self.assertIn("article_link_removed", codes)
        attachment = manifest["attachments"][0]
        self.assertEqual(attachment["name"], "picture.png")
        self.assertEqual(attachment["article_key"], child_a["key"])
        self.assertEqual(attachment["checksum"], self.image.checksum)
        self.assertIn(attachment["file"], files)
