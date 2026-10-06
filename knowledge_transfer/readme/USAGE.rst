Export
~~~~~~

#. Go to *Knowledge > Transfer > Export*, or select articles in the
   *Knowledge > Articles* list and use *Action > Export*.
#. Choose the root articles to export; their sub-articles are included
   automatically. Only root articles of your own Knowledge are offered. From
   the list view action, selected sub-articles are ignored.
#. Click *Export*: a ``knowledge_export_<YYYYMMDD_HHMM>.zip`` file is
   downloaded.

Import
~~~~~~

#. In the target database, go to *Knowledge > Transfer > Import*.
#. Upload the ZIP file and click *Import*.
#. The result shows the number of articles and attachments created, the
   list of warnings (references that could not be transferred) and an
   *Open container* button.
#. The imported trees live in your private section, under
   ``Artículos importados Zinapsia``: **nobody else can see them**. Move,
   rename and reorganize them to the *Workspace* or *Shared* sections so
   other users can access them.

Known limitations
~~~~~~~~~~~~~~~~~

* If the source and target Odoo versions differ, the import still runs but
  a warning is added to the report; embedded components may need a manual
  review.
* Embedded views of other apps, saved filters of embedded views and
  relational property values are not transferred (see the description).
* Translations of article titles and stage names are not transferred: only
  the value in the exporting user's language travels.
* Attachments stored as external URLs are imported as URL attachments, still
  pointing to the same external address.
