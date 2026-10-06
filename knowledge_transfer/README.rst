=======================================
Transferencia de artículos de Knowledge
=======================================

Export Knowledge articles from one Odoo database and import them into
another one, as a ZIP file. Built for go-lives: copy the Knowledge content
prepared in a staging or template database into the customer's database.

**Requires Odoo Enterprise** (it depends on the ``knowledge`` module).

* **Export**: each selected article is exported with all its sub-articles,
  embedded images, files and cover. Selecting an article and one of its
  descendants does not duplicate anything. Archived and trashed articles are
  skipped. Articles are read with the exporting user's own rights.
* **Import**: never overwrites, moves or deletes anything. The content is
  created in the importing user's **private** section, under a root article
  named ``Artículos importados Zinapsia`` (created the first time, reused
  afterwards). Each exported tree becomes a child of that container named
  ``<original name> - YYYY-MM-DD HH:MM`` (import date and time in the user's
  timezone). Importing the same ZIP twice creates two independent copies.
* The whole import runs in a single transaction: if anything fails, nothing
  is created.

What is transferred
-------------------

* Hierarchy and order of the articles, title, emoji icon, body, full width
  option.
* Images and files used in the body (as new attachments, with new ids and
  access tokens), including the original version of cropped images.
* Cover image and its vertical position.
* Article items: item flag, stages (name, order, folded), property
  definitions and non-relational property values.
* Links between articles of the same ZIP, article shortcuts, article index
  blocks and embedded item views (remapped to the new articles).
* Portable embedded blocks: foldable sections, toggle blocks, clipboard,
  table of contents, videos, drawings, captions, code blocks.

What is NOT transferred
-----------------------

* Members, permissions, visibility and favorites: they belong to each
  database. Imported articles are private to the importing user.
* Version history, comments (threads and their markers in the body), chatter
  messages, activities and the attachments of the chatter.
* Attachments of an article that are not used in its body or cover.
* The *locked* flag, templates (template articles are never exported).
* Values of relational (many2one / many2many) properties.

References that cannot travel
-----------------------------

The body of an article holds ids that only make sense in its own database.
On export they are replaced by portable markers; on import the markers are
resolved against the newly created records. **No id of the source database
is ever kept**: anything that cannot be resolved is neutralized (its visible
text is kept, the link or id is dropped) and listed in the import report:

* links and shortcuts to articles that are not part of the export;
* links to records of other models (``/odoo/res.partner/3``...), and images
  of other models (avatars...);
* images or files the exporting user cannot read, or that no longer exist;
* embedded views inserted from other apps, and unsupported embedded
  components, replaced by a ``[Embedded content not transferred: ...]`` text;
* saved filters of embedded item views.

ZIP format (``format_version`` 1)
---------------------------------

::

    manifest.json
    articles/<key>/body.html
    attachments/<n>__<filename>

``manifest.json`` holds ``format_version``, the source Odoo series
(``odoo_series``), the UTC export date (``exported_at``), the ``articles``
(``key``, ``parent_key``, ``sequence``, ``name``, ``icon``, ``full_width``,
``is_article_item``, ``body``, ``cover``, ``stages``, ``stage_key``,
``properties_definition``, ``properties``, ``attachments``), the
``attachments`` (``index``, ``file``/``url``, ``name``, ``mimetype``,
``checksum``, ``article_key``, ``original``) and the export ``warnings``.
Keys are local to the ZIP, never database ids. Bodies reference articles
with ``kt-article:<key>`` and attachments with ``kt-attachment:<n>``.

**Table of contents**

.. contents::
   :local:

Configuration
=============

No configuration is needed.

The *Knowledge > Transfer* menu and the *Export* action of the article list
are only available to users with the **Administration / Settings** access
right (``base.group_system``), which is the group Knowledge itself uses for
its administration features. The restriction is also enforced on the
server, not only by hiding menus.

Note that Knowledge lets administrators read every article of the database,
including other users' private articles, so an administrator can export any
of them.

The import safety limits (maximum number of files and maximum uncompressed
size of the ZIP) are constants at the top of
``models/knowledge_transfer_mixin.py``.

Usage
=====

Export
------

#. Go to *Knowledge > Transfer > Export*, or select articles in the
   *Knowledge > Articles* list and use *Action > Export*.
#. Choose the articles to export (their sub-articles are included).
#. Click *Export*: a ``knowledge_export_<YYYYMMDD_HHMM>.zip`` file is
   downloaded.

Import
------

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
-----------------

* If the source and target Odoo versions differ, the import still runs but
  a warning is added to the report; embedded components may need a manual
  review.
* Embedded views of other apps, saved filters of embedded views and
  relational property values are not transferred (see the description).
* Translations of article titles and stage names are not transferred: only
  the value in the exporting user's language travels.
* Attachments stored as external URLs are imported as URL attachments, still
  pointing to the same external address.

Bug Tracker
===========

Bugs are tracked on `GitHub Issues
<https://github.com/devzinapsia/knowledge/issues>`_.

Credits
=======

Authors
-------

* Zinapsia
