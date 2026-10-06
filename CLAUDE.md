# Zinapsia — Odoo development project memory

This file is generic and is kept in sync across multiple repositories and
machines — every Odoo module development repo, and every client/odoo.sh
deployment repo, whether opened on a macOS or a Windows machine. Only the
section relevant to the repo you are actually in applies, and within it,
only the OS-specific paths for the machine you're actually on. Detect both
before doing anything:

- If it contains Odoo module folders (each with its own `__manifest__.py`),
  it's a **module development repo** → use Section A.
- If it has a `.gitmodules` file referencing other git repos (e.g.
  `zinapsia/*`, `ingadhoc/*`, `OCA/*`), it's a **client/deployment repo** →
  use Section B.

## Company info (used in every manifest / LICENSE / README)

- Legal name: Zinapsia SRL (used in the LICENSE file's copyright line)
- Manifest `author` / README "Credits > Authors": just "Zinapsia" (no
  "SRL") — this is the string Odoo's Apps list groups modules by, and it
  must match exactly across all modules or they split into separate
  author groups in the UI. Don't use "Zinapsia SRL" here even though it's
  the legal name.
- Website: https://www.zinapsia.com
- Dev contact: dev@zinapsia.com
- GitHub org: https://github.com/devzinapsia

## Things to always ask — don't assume, don't skip

1. **Brand-new module**: should it be `auto_install = True` (installs
   automatically as soon as its dependencies are present), or a regular
   opt-in module (`auto_install = False`, the default)?
2. **New standalone model with its own ABM** (a new model with its own
   list/form views, i.e. a new "table" the user manages, like a
   classification or configuration catalog): ask —
   - Does it need the chatter (`mail.thread` / `mail.activity.mixin`,
     `message_ids`/`activity_ids` fields and the chatter widget in the
     form view)? Don't add it by default.
   - Which fields should be available as filters in its search view, and
     which (if any) as default group-by options?
3. **New field added to an existing model** (e.g. adding a field to
   `account.move`, `res.partner`, etc.): ask —
   - Should it be searchable/filterable from the search bar?
   - Should it be available as a "Group By" option?
   - Should it be added as an optional column in the relevant list/grid
     view (`optional="hide"`)?
   Don't assume any of these — a new field is not automatically wired into
   search/group-by/grid just because a previous module did it that way.

---

## Section A — Module development repos (e.g. account-financial-tools)

### Environment
- OS: macOS or Windows, depending on the machine. On Windows this file is
  used from Git Bash (MINGW64, bundled with Git for Windows), since the
  commands elsewhere in this file use bash/POSIX syntax (`grep`,
  forward-slash paths, etc.); if you're actually on plain PowerShell
  instead, flag it — `grep` isn't native there (`Select-String` is the
  equivalent) and Git Bash-style paths like `/e/zinapsia/...` need to
  become `E:\zinapsia\...`.
- Odoo 19 source, used for tests and to confirm real view/menu XML ids
  before writing any xpath (never guess these from memory):
  - macOS: `/Users/pablocampo/devzinapsia/odoo19`
  - Windows: `E:\zinapsia\odoo\19`
- Odoo 18 source, same purpose, for modules targeting 18.0:
  - macOS: `/Users/pablocampo/devzinapsia/odoo18`
  - Windows: `E:\zinapsia\odoo\18`
- Always confirm the current git branch matches the Odoo version you're
  developing for (branch `19.0` → check against the Odoo 19 source, branch
  `18.0` → Odoo 18 source). Run `git branch` and check before starting;
  don't assume the checked-out branch is the right one.
- Module development repos (this repo and its siblings) — on Windows, live
  under `E:\zinapsia\devzinapsia\<repo>`. No fixed parent path is enforced
  on macOS.

### Local test databases & client backups (Windows)
- `E:\zinapsia\databases` holds local Odoo test database dumps, including
  client odoo.sh backups (`.zip`) kept here for local reproduction/
  debugging of client-reported issues.
- Before creating a fresh test database for the install/uninstall cycle
  (see Testing & validation below), check this folder for an existing
  dump that already matches the target Odoo version/client instead of
  starting from scratch.
- An odoo.sh backup `.zip` normally contains `dump.sql` + a `filestore/`
  folder + `manifest.json`. Restoring locally means extracting it,
  loading `dump.sql` into a fresh Postgres database (`psql`/`pg_restore`
  depending on format), and copying `filestore/` into that database's
  local Odoo filestore path. Confirm the exact restore steps with the
  user before improvising if a particular backup's format is unfamiliar
  — don't guess.
- No equivalent folder is confirmed yet for macOS — ask before assuming
  one exists there instead of guessing a path.

### Module folder naming
- English, snake_case, descriptive of the feature. This is the technical
  name only (folder, Python package, xmlids) — it stays English even
  though the manifest `name` (see below) is Spanish.

### Standard module contents (every module must have all of this)
```
<module_name>/
├── __init__.py
├── __manifest__.py
├── LICENSE                    (full AGPL-3 text, same as repo root)
├── README.rst                 (documents the functionality — see below)
├── models/
├── views/
├── security/
├── data/                       (config/seed data, if any, noupdate="1")
├── i18n/ (.pot, es.po, es_AR.po — always fully translated, no empty msgstr)
├── static/description/index.html
├── readme/ (DESCRIPTION.rst, CONFIGURE.rst, USAGE.rst — source fragments)
└── tests/
```
- `README.rst` at the module root must document what the module does, how
  to configure it, and how to use it. Build it from the `readme/*.rst`
  fragments (OCA convention), plus a "Bug Tracker" section linking to this
  module's own GitHub repo URL, and a "Credits > Authors" section listing
  "Zinapsia". Don't skip this file — `static/description/index.html`
  alone is not enough, that one is only for the Apps Store listing.

### Manifest fields (mandatory on every module)
- `license`: `"AGPL-3"`
- `author`: `"Zinapsia"`
- `website`: `"https://www.zinapsia.com"`
- Also put this module's own GitHub repo URL in `README.rst`'s "Bug
  Tracker" section (not in the manifest — the manifest `website` key only
  holds one URL, and that slot is reserved for the company site).
- `name` and `summary`: written directly in **Spanish** as the source
  text (e.g. `"name": "Notificaciones de vencimientos de pago"`), not
  English-with-po-translation like other UI strings (see Coding language
  rule 2 below) — these are what shows in the Apps list, and translating
  a module's own `ir.module.module.shortdesc`/`summary` via po requires
  referencing `base.module_<technical_name>` (an `ir.model.data` entry
  Odoo creates itself, in the `base` module's namespace, not the
  module's own), which is easy to get wrong and not worth the fragility
  for text that only ever needs to be Spanish in practice. Mirror the
  Spanish name in `README.rst`'s title heading and in
  `static/description/index.html`'s `<title>`/`<h2 class="oe_slogan">`
  too, so the module's identity is consistent everywhere it's named;
  the rest of those files' prose is unaffected by this rule.
- This Spanish-name rule applies going forward to new modules and to
  modules touched for other reasons — it is not a mandate to go back and
  retroactively rename every existing module's manifest `name` across
  every repo; do that only if separately asked.

### Coding language rules (strict)
1. All Python/XML/JS code and ALL comments/docstrings: English, no
   exceptions.
2. All UI-facing strings (field `string=`, menu/action `name=`, help text):
   English source, fully translated in `es.po` and `es_AR.po` — never leave
   `msgstr ""` empty. Exception: the module's own manifest `name`/
   `summary` (the Apps-list display name) — see "Manifest fields" below,
   those are Spanish source directly, no po entry.
3. Business/master-data literal seed values may stay in Spanish when
   they're proper nouns or client-facing business terms — confirm with the
   user case by case, don't assume.
4. Label capitalization: sentence case only — first letter capitalized,
   rest lowercase, except proper nouns (e.g. "Agreed payment method", not
   "Agreed Payment Method"). Applies to English source AND Spanish
   translations, on every field/menu/action label added.

### Icons for links inside outgoing emails
- An outgoing email is a static HTML document opened in a third-party
  mail client (Outlook, Gmail, etc.) — a completely different rendering
  environment from the live Odoo web client. This means TWO things that
  look like reasonable icon choices both fail there, so don't reach for
  either:
  - A `<i class="fa-...">`/`icon="fa-..."` glyph, or copying one from an
    Odoo **view** (e.g. a list view's `<button icon="fa-external-link"/>`,
    as in `arca_bills_comparation`'s results grid) — that works there
    only because it's rendered by the live web client, which has Font
    Awesome loaded; an email has none of that.
  - An inline SVG embedded as a `data:image/svg+xml` `<img>` — looks
    right and is self-contained, but tested in real clients (Outlook)
    and confirmed broken: the image fails to load, leaving a
    broken-image box with the `alt` text showing next to it.
- Zinapsia's standard for "open this record" links inside an email body:
  make the record's own text (document number, name, etc.) the
  hyperlink itself — underlined, standard `<a>` styling, no icon at all:
  ```python
  from markupsafe import Markup

  link = Markup('<a href="%s" title="%s">%s</a>') % (url, "view document", label)
  ```
  Simpler to read and doesn't cost extra column width, and was preferred
  over an icon once tried (feedback: "más natural... no ocupa espacio").
  Only reach for a separate `↗` (U+2197 NORTH EAST ARROW) as plain link
  text when there's no natural label to hyperlink (e.g. a bare "view"
  action with nothing else in that cell) — never an image/icon font for
  either case; both were tried and failed to render in real clients (see
  above).

### View development rules
- Never assume a view id, menu id, or xpath target from memory — confirm it
  against the real Odoo source path above (or against how it was already
  solved in an existing sibling module in this same repo). If it can't be
  confirmed, leave an explicit `TODO` comment and flag it instead of
  guessing.
- `account.move` has a single shared form view across all `move_type`
  values (invoices, bills, credit/debit notes) — use
  `invisible="move_type not in (...)"` to scope a field, instead of
  duplicating views.
- Modern view syntax only: `readonly="..."`, `invisible="..."` as direct
  attributes — never `attrs={}` (deprecated).
- Extra grid/list columns that shouldn't show by default: `optional="hide"`.
- Search view "Group By" filters: available as an option, not
  auto-activated, unless the user explicitly asks for auto-activation.

### Security patterns
- `ir.model.access.csv`: read access for `account.group_account_invoice`,
  full CRUD for `account.group_account_manager` (adjust groups to the
  module's actual domain when it's not accounting-specific).
- Multi-company models: `ir.rule` domain
  `['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`
  (empty `company_id` = shared across all companies).

### Testing & validation before showing a diff
1. `python3 -m py_compile` on all `.py` files on macOS. On Windows Git
   Bash, confirm first whether `python` or `python3` resolves to the right
   interpreter (`python --version` / `python3 --version`) — don't assume
   `python3` like on macOS/Linux.
2. Well-formed XML check on all `.xml` files.
3. TransactionCase tests covering the core scenarios of the module.
4. **Always run this install/uninstall cycle against the matching local
   Odoo source** (the 19 or 18 path above, whichever matches the branch)
   before considering the module done, using a local test database (on
   Windows, see "Local test databases & client backups" above for
   existing dumps to start from):
   - Install the module. Confirm it installs with no errors.
   - Verify it's actually active (e.g. `-i <module> --stop-after-init` exits
     cleanly, and/or check `ir.module.module` state is `installed`).
   - Uninstall the module (`-u`/`--uninstall` as applicable, or via the
     Apps list). Confirm it uninstalls cleanly with no leftover errors.
   - Install it again. Confirm the second install also succeeds cleanly.
   - Report the outcome of all four steps explicitly — don't just say
     "tests passed" without showing this cycle ran.
   - If there's no local test database set up yet to run this against, ask
     what's needed to set one up before marking the module as ready for
     review — don't skip this step silently.

### Git workflow
- Always show `git status` and the full `git diff` before committing.
- Never commit or push without explicit user confirmation — ask first,
  every time.
- Commit message format (English): `[ADD] <module_name>: <short summary>`.

### Hard-won Odoo 19 debugging lessons
- A `.po` file's `#:` occurrence comments aren't cosmetic — Odoo's
  translation loader uses each one to decide which specific record/field
  gets the `msgstr` written into its JSONB-translated column. Two records
  can share the exact same English source text as a plain Python string,
  but if only one of them has a `#:` reference in the `.po` file, only
  that one gets translated; the other silently stays in English even
  though the "same" msgid already has a translation elsewhere. Concretely:
  adding a new `ir.actions.server` whose `name` reuses an existing button's
  label (e.g. both "Reprocess") does NOT automatically translate the new
  action's menu entry — add its own
  `#: model:ir.actions.server,name:<module>.<xml_id>` line under that same
  msgid in every `.po`/`.pot` file, or it ships English-only in the
  Actions (⚙) menu regardless of how many other places already show it
  correctly translated.
- A `related=` field without its own `string=`/`help=` still gets its own
  `ir.model.fields` row on the model that declares it — translating the
  target field's `field_description`/`help` does NOT translate the
  related field's copy shown wherever *it* renders (e.g. a
  `res.company` field mirrored onto `res.config.settings`). Add `#:`
  references for both `field_<company_table>__<name>` and
  `field_<other_table>__<name>` under the same msgid, or the settings
  screen quietly stays in English while the underlying company field
  translates fine. The same non-inheritance applies to `domain=`: a
  `related=` Many2many/Many2one on `res.config.settings` does NOT pick
  up the target field's `domain=` either — repeat it explicitly on the
  related field too, or a picker on the settings screen (e.g. an
  "accounts to include" field restricted to active bank/cash accounts
  on `res.company`) silently offers everything, archived records
  included, even though the company field's own domain is correct.
- `self.assertRaises(...)` in Odoo's `TransactionCase` wraps the call in a
  cursor savepoint that rolls back once the expected exception is caught —
  this erases every change the code made before raising, not just the
  exception itself. If a test needs to inspect state *after* an expected
  exception (e.g. confirming a payment stayed blocked, with the right
  activity/message left behind), use a manual `try/except` +
  `self.fail(...)` instead of `self.assertRaises()`.
- When overriding a method on a core model that *other installed modules
  also override* (e.g. `account.payment.action_post()`), never assume your
  override is the one that actually runs, or that it runs at all. Verify
  with `inspect.getsourcefile(type(record).method_name)` /
  `inspect.getsourcelines(...)` in `odoo-bin shell` before spending time
  debugging logic that never executes — the real MRO owner is sometimes a
  third-party module loaded later.
- A field meant to identify "the related record" that a user will also
  need to reference from a *visual* domain/filter builder (e.g. the
  invoice linked to a payment) should reuse an existing, obviously-named
  core field (like `invoice_ids`) rather than a new custom technical field
  with a different label. Users naturally pick the field with the
  intuitive name in the picker; if that's not the one your code actually
  populates, conditions silently never match and the bug looks like
  "nothing works" with no error anywhere.
- When syncing a relational field from another source on every change, use
  `Command.set` (replace) not `Command.link` (add-only) — otherwise stale
  entries accumulate over time, and can leak into *other* modules that
  also read that same field, not just your own logic.
- If a module needs to optionally interoperate with a third-party module
  that isn't installed in every deployment reusing this repo (e.g.
  ingadhoc's `account_payment_pro` on some clients but not others), build
  a separate glue module (`<base_module>_<other_module>`,
  `depends=[base, other]`, `auto_install=True`) rather than hard-depending
  on the optional module from the base one, or littering it with defensive
  `if field in self._fields` checks. Keeps the base module portable across
  every client repo that reuses it.
- Some third-party modules add their own separate, *unnamed* `<notebook>`
  to a form instead of extending a core model's named one (e.g.
  `l10n_latam_check` does this on `account.payment`, instead of using the
  core `payment_notebook`). Inserting a new tab into the "obviously
  correct" named notebook can silently render as a disconnected second tab
  strip. Before assuming a tab landed where you put it, check the actual
  resolved view (`env['model'].get_view(view_id=..., view_type='form')`
  and inspect the `<notebook>` elements in the returned arch) — and use
  `position="move"` plus a high view `priority` to relocate it if needed.
- A checkbox nested inside a `<setting>` block, meant to sit inline with
  its own **non-bold** label on one row: a plain `<field name="x"/>`
  followed directly by `<label for="x" class="fw-normal me-1"/>` — no
  wrapping div, no `d-flex`, no `<br/>`. Copy point_of_sale's "Show
  product images"/"Show category images" checkboxes verbatim rather than
  improvising. Don't try to un-bold the label with an inline
  `style="font-weight: normal"` — even with `!important` it silently
  does nothing, because whatever the `<setting>` element's compiler does
  to descendant `<label>` tags doesn't preserve arbitrary `style`
  attributes; only a `class` (here `fw-normal`, a Bootstrap 5 utility
  that ships its own `!important`) survives. Also don't reach for
  `o_setting_left_pane`/`o_setting_right_pane` for a plain sub-option —
  that pair is for a standalone boxed toggle and renders stacked with a
  stray border in this nested context.
- To verify a fix against a client's actual third-party modules instead of
  guessing: point a temporary `--addons-path` at that client's deployment
  repo submodules (e.g. `<client-repo>/ingadhoc/*`, `<client-repo>/OCA/*` —
  on Windows, `E:\zinapsia\clientes\<client>\ingadhoc\*`,
  `E:\zinapsia\clientes\<client>\OCA\*`) and install for real in a scratch
  local database. Reading those
  submodules for this kind of investigation/testing is fine and often the
  only reliable way to reproduce a client-specific bug — the "never touch
  `ingadhoc/*`/`OCA/*`" rule (Section B) is about not *modifying* them, not
  about being unable to read/install them locally for diagnosis.

---

## Section B — Client / odoo.sh deployment repos (e.g. grupolara)

### Environment
- These repos deploy Odoo for a specific client via odoo.sh, and consume
  module repos (like account-financial-tools) as git submodules, typically
  grouped under a `zinapsia/` folder alongside other submodule groups such
  as `ingadhoc/*` and `OCA/*`.
- On Windows, these client repos live under `E:\zinapsia\clientes\<client>`,
  one subfolder per client. No fixed parent path is enforced on macOS.
- **Never touch `ingadhoc/*` or `OCA/*` submodules unless explicitly
  asked** — only work with `zinapsia/*`.
- Confirm the tracked branch of a submodule with:
  `grep -A5 "<submodule-name>" .gitmodules`

### Golden rules for submodule commands
1. Always run submodule commands from the **repo root**, never from inside
   a subfolder — a submodule path is relative to the repo root, and
   running the command elsewhere can make git silently update *all*
   submodules instead of just the intended one.
2. Always scope the update to the specific path:
   ```bash
   git submodule update --remote --merge -- zinapsia/<module-repo>
   ```
3. `git checkout <branch>` does NOT auto-realign submodule working trees to
   what that branch expects. After switching branches, check `git status`:
   if submodules other than the intended one show up as "modified (new
   commits)", realign them with
   `git submodule update -- <path1> <path2> ...`, or configure
   `git config submodule.recurse true` once, locally, to avoid this
   going forward.

### Standard update flow (repeat per branch — pointers are independent per branch)
```bash
cd <repo root>   # on Windows Git Bash, e.g.: cd /e/zinapsia/clientes/<client>
git checkout <branch>
git submodule update --remote --merge -- zinapsia/<module-repo>
git status   # must show ONLY the intended submodule as modified
git add zinapsia/<module-repo>
git commit -m "Update <module-repo> submodule: <short summary of what changed>"
git push origin <branch>
```

### Branch caution
- `staging2` is the primary branch for first-round testing of new submodule
  changes.
- Never push to a production branch (e.g. `main`) without explicit
  confirmation in the conversation that testing passed on a staging branch
  first — even if the update already went out to `staging2`/`staging`.

### A pushed submodule update may need a rebuild to actually take effect
Updating the submodule pointer and pushing does NOT guarantee the running
Odoo server picks up the new code. On odoo.sh, a push to a linked branch
usually triggers an automatic rebuild — but if a user reports "I pushed the
fix and it's still broken," don't assume the code itself is wrong before
confirming a rebuild actually ran:
1. Ask the user to check the module's installed version in **Apps** (should
   match the version in the latest commit's `__manifest__.py`). If it's
   older, the update never ran on that server at all.
2. If the version *does* match but behavior is still the old one, the DB
   update likely ran (picking up view/field/version changes) but the
   long-running web workers may still have the old Python source loaded in
   memory — ask the user to trigger an explicit rebuild (not just an app
   update) and retest.
View/XML changes are less likely to hit this than Python logic changes,
since views are re-read from the DB on every request, but a rebuild is the
safe first troubleshooting step either way when "it looks like my fix
should have worked but didn't."
