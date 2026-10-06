import base64

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import KnowledgeTransferCase, make_zip


@tagged("post_install", "-at_install")
class TestKnowledgeTransferSecurity(KnowledgeTransferCase):

    def test_non_admin_cannot_create_wizards(self):
        for model in ("knowledge.transfer.export.wizard", "knowledge.transfer.import.wizard"):
            with self.subTest(model=model), self.assertRaises(AccessError):
                self.env[model].with_user(self.internal_user).create({})

    def test_non_admin_cannot_run_wizard_actions(self):
        """Server-side checks, even on a wizard record obtained otherwise."""
        export_wizard = self.env["knowledge.transfer.export.wizard"].create(
            {"article_ids": [(6, 0, self.root.ids)]})
        import_wizard = self.env["knowledge.transfer.import.wizard"].create({
            "zip_file": base64.b64encode(make_zip({"x.txt": "x"})),
        })
        with self.assertRaises(AccessError):
            export_wizard.with_user(self.internal_user).sudo(False).action_export()
        with self.assertRaises(AccessError):
            import_wizard.with_user(self.internal_user).sudo(False).action_import()
        with self.assertRaises(AccessError):
            self.env["knowledge.transfer.export.wizard"].with_user(self.internal_user) \
                .action_open_with_articles(self.root.ids)

    def test_admin_can_export_and_import(self):
        wizard = self.import_zip(self.export_zip(self.root))
        self.assertEqual(wizard.state, "done")
