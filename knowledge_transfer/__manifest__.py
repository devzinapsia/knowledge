{
    "name": "Transferencia de artículos de Knowledge",
    "version": "19.0.1.0.0",
    "category": "Productivity/Knowledge",
    "summary": "Exportar e importar árboles de artículos de Knowledge entre bases mediante un ZIP",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "license": "AGPL-3",
    "depends": [
        "knowledge",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/knowledge_transfer_export_wizard_views.xml",
        "wizard/knowledge_transfer_import_wizard_views.xml",
        "views/knowledge_transfer_menus.xml",
    ],
    "installable": True,
    "auto_install": False,
}
