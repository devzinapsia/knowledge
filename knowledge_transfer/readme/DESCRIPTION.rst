Export Knowledge articles from one Odoo database and import them into
another one, as a ZIP file. Built for go-lives: copy the Knowledge content
prepared in a staging or template database into the customer's database.

**Requires Odoo Enterprise** (it depends on the ``knowledge`` module).

* **Export**: you select **root articles** only (the ones shown at the top
  level of your Knowledge sidebar); each one is exported with all its
  sub-articles, embedded images, files and cover. Archived and trashed
  articles are skipped. Only your own Knowledge is offered: articles you can
  see and access through Knowledge permissions (workspace articles visible to
  you, your private and shared articles), never other users' private
  articles, even for administrators.
* **Import**: never overwrites, moves or deletes anything. The content is
  created in the importing user's **private** section, under a root article
  named ``Artículos importados Zinapsia`` (created the first time, reused
  afterwards). Each exported tree becomes a child of that container named
  ``<original name> - YYYY-MM-DD HH:MM`` (import date and time in the user's
  timezone). Importing the same ZIP twice creates two independent copies.
* The whole import runs in a single transaction: if anything fails, nothing
  is created.

What is transferred
~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~

* Members, permissions, visibility and favorites: they belong to each
  database. Imported articles are private to the importing user.
* Version history, comments (threads and their markers in the body), chatter
  messages, activities and the attachments of the chatter.
* Attachments of an article that are not used in its body or cover.
* The *locked* flag, templates (template articles are never exported).
* Values of relational (many2one / many2many) properties.

References that cannot travel
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
