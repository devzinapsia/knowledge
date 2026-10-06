No configuration is needed.

The *Knowledge > Transfer* menu and the *Export* action of the article list
are only available to users with the **Administration / Settings** access
right (``base.group_system``), which is the group Knowledge itself uses for
its administration features. The restriction is also enforced on the
server, not only by hiding menus.

Knowledge lets administrators read every article of the database through
access rights, including other users' private articles. The export does not
rely on that: it only offers and exports the articles the user can see in
their own Knowledge sidebar and access through Knowledge permissions
(members and internal permission), both for the selected root articles and
for their sub-articles.

The import safety limits (maximum number of files and maximum uncompressed
size of the ZIP) are constants at the top of
``models/knowledge_transfer_mixin.py``.
