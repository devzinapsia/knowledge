"""Rewrite every database-specific reference found in a Knowledge article body.

The same traversal is used in both directions:

* on export, the resolver turns real ids (``/web/image/42``, ``data-res_id="7"``,
  embedded props ``{"id": 42}``...) into portable markers (``kt-attachment:3``,
  ``kt-article:a2``);
* on import, the resolver turns those markers into the ids of the records
  created by the import.

Any reference the resolver cannot map (an article that did not travel in the
ZIP, a missing attachment, a link to a record of another model, an embedded
component whose props cannot be made portable...) is neutralized: the visible
text is kept, the reference is dropped and a warning is recorded. This
guarantees that no id of the source database survives the round trip, since
on import a raw numeric id is never accepted, only markers.
"""

import json
import re
from urllib.parse import parse_qs, urlsplit

from lxml import html
from markupsafe import escape

ARTICLE_MARKER = "kt-article:"
ATTACHMENT_MARKER = "kt-attachment:"

# Embedded components whose props hold no database id at all.
PORTABLE_EMBEDDINGS = {
    "caption",
    "clipboard",
    "draw",
    "foldableSection",
    "readonlySyntaxHighlighting",
    "syntaxHighlighting",
    "tableOfContent",
    "toggleBlock",
    "video",
}
# Embedded views can only be remapped when they list the items of an article
# (their context then only references that article). Views inserted from other
# apps hold domains/contexts with ids of other models and cannot be ported.
KNOWLEDGE_ITEM_ACTIONS = {
    "knowledge.knowledge_article_item_action",
    "knowledge.knowledge_article_item_action_stages",
    "knowledge.knowledge_article_action_item_calendar",
}
VIEW_CONTEXT_ARTICLE_KEYS = ("active_id", "default_parent_id")
INLINE_TAGS = {"a", "span", "img", "b", "i", "u", "em", "strong", "small", "code", "font"}
ID_ATTRIBUTES = ("data-oe-model", "data-oe-id")

_RE_ATTACHMENT_PATH = re.compile(r"^/web/(?P<kind>image|content)/(?P<id>\d+)(?:-[0-9a-zA-Z]+)?(?:/.*)?$")
_RE_ATTACHMENT_MODEL_PATH = re.compile(r"^/web/(?P<kind>image|content)/ir\.attachment/(?P<id>\d+)(?:/.*)?$")
_RE_RECORD_FIELD_PATH = re.compile(r"^/web/(?:image|content)/[\w.]+/\d+(?:/.*)?$")
_RE_WEB_QUERY_PATH = re.compile(r"^/web/(?P<kind>image|content)/?$")
_RE_ARTICLE_PATH = re.compile(r"^/knowledge/article/(?P<id>\d+)/?$")
_RE_ODOO_ARTICLE_PATH = re.compile(r"^/odoo/(?:.+/)?(?:knowledge|knowledge\.article|articles)/(?P<id>\d+)/?$")
_RE_ODOO_RECORD_PATH = re.compile(r"^/odoo/.*/\d+(?:/.*)?$")
_RE_KNOWLEDGE_OTHER_PATH = re.compile(r"^/knowledge/article/invite/")
_RE_ATTACHMENT_MARKER = re.compile(
    r"^kt-attachment:(?P<index>\d+)(?::(?P<kind>image|content))?(?P<download>\?download=true)?$")
_RE_ARTICLE_MARKER = re.compile(r"^kt-article:(?P<key>[A-Za-z0-9_-]+)(?P<fragment>#.*)?$")
_RE_STYLE_URL = re.compile(r"url\(\s*(['\"]?)(?P<url>[^)'\"]*)\1\s*\)")

# Reference types returned by ``parse_url``.
REF_ARTICLE = "article"
REF_ATTACHMENT = "attachment"
REF_RECORD = "record"


class BodyResolver:
    """Map references found in a body. Subclassed by the export and import sides.

    A ``ref`` is either an ``int`` (a real id read from the HTML) or a ``str``
    (a marker key). Every method returns ``None`` when the reference cannot be
    mapped, which makes the rewriter neutralize it.
    """

    def __init__(self):
        self.warnings = []
        self.article_key = None

    def warn(self, code, detail=""):
        self.warnings.append({"article_key": self.article_key, "code": code, "detail": detail or ""})

    def article(self, ref):
        """Return the token stored in ids slots (``data-res_id``, props)."""
        raise NotImplementedError

    def article_url(self, token, fragment):
        raise NotImplementedError

    def attachment(self, ref):
        """Return an opaque attachment token, or None."""
        raise NotImplementedError

    def attachment_id(self, token):
        """Return what goes in ``data-attachment-id``-like slots."""
        raise NotImplementedError

    def attachment_url(self, token, kind, download):
        raise NotImplementedError

    def attachment_file_data(self, token, file_data):
        """Return the updated ``fileData`` props of an embedded file."""
        raise NotImplementedError


def parse_url(url, source_origins=()):
    """Classify a URL found in a body.

    :param source_origins: ``scheme://host`` origins considered local (besides
      relative URLs), e.g. the ``web.base.url`` of the database.
    :return: ``(ref_type, ref, extra)`` or ``None`` for URLs to keep untouched.
      ``ref`` is an int for real URLs, a str for markers. ``extra`` holds
      ``kind``/``download`` for attachments and ``fragment`` for articles.
    """
    if not url:
        return None
    url = url.strip()
    marker = _RE_ATTACHMENT_MARKER.match(url)
    if marker:
        return REF_ATTACHMENT, marker["index"], {
            "kind": marker["kind"] or "content", "download": bool(marker["download"])}
    marker = _RE_ARTICLE_MARKER.match(url)
    if marker:
        return REF_ARTICLE, marker["key"], {"fragment": marker["fragment"] or ""}

    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme or parts.netloc:
        origin = f"{parts.scheme}://{parts.netloc}".lower()
        if origin not in source_origins:
            return None  # external URL, portable as is
    path = parts.path or ""
    query = parse_qs(parts.query)
    download = query.get("download", [""])[0] in ("true", "1")

    match = _RE_ATTACHMENT_PATH.match(path) or _RE_ATTACHMENT_MODEL_PATH.match(path)
    if match:
        return REF_ATTACHMENT, int(match["id"]), {"kind": match["kind"], "download": download}
    match = _RE_WEB_QUERY_PATH.match(path)
    if match and query.get("id"):
        model = query.get("model", ["ir.attachment"])[0]
        if model == "ir.attachment" and query["id"][0].isdigit():
            return REF_ATTACHMENT, int(query["id"][0]), {"kind": match["kind"], "download": download}
        return REF_RECORD, None, {}
    if _RE_RECORD_FIELD_PATH.match(path):
        return REF_RECORD, None, {}
    match = _RE_ARTICLE_PATH.match(path) or _RE_ODOO_ARTICLE_PATH.match(path)
    if match:
        fragment = f"#{parts.fragment}" if parts.fragment else ""
        return REF_ARTICLE, int(match["id"]), {"fragment": fragment}
    if _RE_ODOO_RECORD_PATH.match(path) or _RE_KNOWLEDGE_OTHER_PATH.match(path):
        return REF_RECORD, None, {}
    if path.startswith("/web") and re.search(r"(^|[&#])id=\d+", parts.fragment or ""):
        return REF_RECORD, None, {}  # legacy /web#id=..&model=.. links
    if path.startswith("/mail/view") and query.get("res_id"):
        return REF_RECORD, None, {}
    return None


def _parse_ref_value(value):
    """Parse an id slot value: a real id (int) or a marker key (str)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            return int(value)
        for prefix in (ARTICLE_MARKER, ATTACHMENT_MARKER):
            if value.startswith(prefix):
                return value[len(prefix):]
    return None


class BodyRewriter:

    def __init__(self, resolver, source_origins=(), neutral_texts=None):
        """
        :param resolver: a :class:`BodyResolver`;
        :param source_origins: origins whose absolute URLs are treated as local;
        :param neutral_texts: callables producing the visible placeholder texts
          (translated by the caller), keys ``image``, ``file``, ``embedded``.
        """
        self.resolver = resolver
        self.source_origins = {origin.lower().rstrip("/") for origin in source_origins if origin}
        self.neutral_texts = neutral_texts or {}

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def rewrite(self, body, article_key):
        self.resolver.article_key = article_key
        if not body or not str(body).strip():
            return ""
        root = html.fragment_fromstring(str(body), create_parent="div")

        for element in root.xpath(".//*[@data-last-history-steps]"):
            del element.attrib["data-last-history-steps"]
        # Comment threads are not transferred: drop their invisible anchors.
        for beacon in root.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " oe_thread_beacon ")]'):
            beacon.drop_tree()

        for element in list(root.xpath(".//*[@data-embedded]")):
            if self._is_attached(element, root):
                self._rewrite_embedded(element)

        for element in list(root.iter()):
            if element is root or not self._is_attached(element, root):
                continue
            if not isinstance(element.tag, str):
                continue  # comments, processing instructions
            self._rewrite_element(element)

        result = escape(root.text or "")
        return str(result) + "".join(html.tostring(child, encoding="unicode") for child in root)

    # ------------------------------------------------------------------
    # Plain elements
    # ------------------------------------------------------------------

    def _rewrite_element(self, element):
        tag = element.tag.lower()
        for attribute in ID_ATTRIBUTES:
            element.attrib.pop(attribute, None)
        element.attrib.pop("srcset", None)

        if element.get("style") and "url(" in element.get("style"):
            element.set("style", _RE_STYLE_URL.sub(self._rewrite_style_url, element.get("style")))

        for attribute in ("data-attachment-id", "data-original-id"):
            if element.get(attribute) is not None:
                token = self._attachment_from_value(element.get(attribute))
                if token is None:
                    del element.attrib[attribute]
                else:
                    element.set(attribute, str(self.resolver.attachment_id(token)))
        if element.get("data-original-src") is not None:
            new_url = self._map_attachment_url(element.get("data-original-src"))
            if new_url:
                element.set("data-original-src", new_url)
            else:
                del element.attrib["data-original-src"]

        if tag == "a":
            self._rewrite_link(element)
            return
        if element.get("data-res_id") is not None:
            # Only article shortcuts carry this attribute in Knowledge bodies.
            token = self._map_article_value(element.get("data-res_id"))
            if token is None:
                del element.attrib["data-res_id"]
            else:
                element.set("data-res_id", str(token))
        if element.get("src") is not None:
            self._rewrite_src(element, tag)

    def _rewrite_link(self, element):
        href = element.get("href")
        res_id = element.get("data-res_id")
        is_article_shortcut = "o_knowledge_article_link" in (element.get("class") or "")
        parsed = parse_url(href, self.source_origins) if href else None
        if parsed is None and is_article_shortcut and res_id is not None:
            ref = _parse_ref_value(res_id)
            parsed = (REF_ARTICLE, ref, {"fragment": ""}) if ref is not None else (REF_RECORD, None, {})
        if parsed is None:
            if res_id is not None:
                del element.attrib["data-res_id"]
            return

        ref_type, ref, extra = parsed
        label = (element.text_content() or "").strip() or (href or "")
        if ref_type == REF_ARTICLE:
            token = self.resolver.article(ref) if ref is not None else None
            if token is None:
                self.resolver.warn("article_link_removed", label)
                self._unwrap(element)
                return
            element.set("href", self.resolver.article_url(token, extra.get("fragment", "")))
            if res_id is not None or is_article_shortcut:
                element.set("data-res_id", str(token))
            return
        if res_id is not None:
            del element.attrib["data-res_id"]
        if ref_type == REF_ATTACHMENT:
            token = self.resolver.attachment(ref)
            if token is None:
                self.resolver.warn("attachment_link_removed", label)
                self._unwrap(element)
                return
            element.set("href", self.resolver.attachment_url(token, extra["kind"], extra["download"]))
            return
        self.resolver.warn("record_link_removed", label)
        self._unwrap(element)

    def _rewrite_src(self, element, tag):
        src = element.get("src")
        parsed = parse_url(src, self.source_origins)
        if parsed is None:
            return
        ref_type, ref, extra = parsed
        token = self.resolver.attachment(ref) if ref_type == REF_ATTACHMENT else None
        if token is not None:
            kind = "image" if tag == "img" else extra["kind"]
            element.set("src", self.resolver.attachment_url(token, kind, False))
            return
        label = element.get("alt") or element.get("title") or src
        self.resolver.warn("image_removed" if tag == "img" else "media_removed", label)
        if tag == "img":
            self._replace_with_text(element, self._neutral_text("image", label))
        else:
            del element.attrib["src"]

    def _rewrite_style_url(self, match):
        url = match["url"]
        parsed = parse_url(url, self.source_origins)
        if parsed is None:
            return match.group(0)
        new_url = self._map_attachment_url(url)
        if new_url:
            return f"url('{new_url}')"
        self.resolver.warn("image_removed", url)
        return "none"

    def _map_attachment_url(self, url):
        parsed = parse_url(url, self.source_origins)
        if not parsed or parsed[0] != REF_ATTACHMENT:
            return None
        token = self.resolver.attachment(parsed[1])
        if token is None:
            return None
        return self.resolver.attachment_url(token, parsed[2]["kind"], parsed[2]["download"])

    def _attachment_from_value(self, value):
        ref = _parse_ref_value(value)
        return self.resolver.attachment(ref) if ref is not None else None

    def _map_article_value(self, value):
        ref = _parse_ref_value(value)
        return self.resolver.article(ref) if ref is not None else None

    # ------------------------------------------------------------------
    # Embedded components
    # ------------------------------------------------------------------

    def _rewrite_embedded(self, element):
        name = element.get("data-embedded")
        if name in PORTABLE_EMBEDDINGS:
            return
        try:
            props = json.loads(element.get("data-embedded-props") or "{}")
        except ValueError:
            props = None
        handler = {
            "file": self._rewrite_embedded_file,
            "view": self._rewrite_embedded_view,
            "viewLink": self._rewrite_embedded_view,
            "articleIndex": self._rewrite_embedded_article_index,
        }.get(name)
        if handler is None or not isinstance(props, dict):
            self._neutralize_embedded(element, name, name)
            return
        new_props = handler(element, props)
        if new_props is not None:
            element.set("data-embedded-props", json.dumps(new_props))

    def _rewrite_embedded_file(self, element, props):
        file_data = props.get("fileData") or {}
        label = file_data.get("name") or file_data.get("filename") or "file"
        ref = _parse_ref_value(file_data.get("id"))
        token = self.resolver.attachment(ref) if ref is not None else None
        if token is None:
            url = file_data.get("url") or ""
            if url and not file_data.get("id") and parse_url(url, self.source_origins) is None:
                return props  # file stored as an external link, portable as is
            self.resolver.warn("file_removed", label)
            self._replace_with_text(element, self._neutral_text("file", label))
            return None
        props["fileData"] = self.resolver.attachment_file_data(token, dict(file_data))
        return props

    def _rewrite_embedded_view(self, element, props):
        view_props = props.get("viewProps") or {}
        label = view_props.get("displayName") or element.get("data-embedded")
        if "actWindow" in view_props or view_props.get("actionXmlId") not in KNOWLEDGE_ITEM_ACTIONS:
            self._neutralize_embedded(element, element.get("data-embedded"), label)
            return None
        context = view_props.get("context") or {}
        for key in VIEW_CONTEXT_ARTICLE_KEYS:
            if key in context:
                token = self._map_article_value(context[key])
                if token is None:
                    self._neutralize_embedded(element, element.get("data-embedded"), label)
                    return None
                context[key] = token
        # Saved filters and search states may hold domains with ids of this
        # database: they cannot be made portable safely.
        removed = bool(view_props.pop("favoriteFilters", None))
        removed |= bool(context.pop("knowledge_search_model_state", None))
        if removed:
            self.resolver.warn("view_filters_removed", label)
        view_props["context"] = context
        props["viewProps"] = view_props
        return props

    def _rewrite_embedded_article_index(self, element, props):
        def remap(entries):
            result = []
            for entry in entries or []:
                if not isinstance(entry, dict):
                    continue
                token = self._map_article_value(entry.get("id"))
                if token is None:
                    self.resolver.warn("index_entry_removed", entry.get("name") or "")
                    continue
                result.append(dict(entry, id=token, childIds=remap(entry.get("childIds"))))
            return result

        if "articles" in props:
            props["articles"] = remap(props["articles"])
        return props

    def _neutralize_embedded(self, element, name, label):
        self.resolver.warn("embedded_removed", f"{name}: {label}" if label and label != name else name or "")
        self._replace_with_text(element, self._neutral_text("embedded", label or name or ""))

    # ------------------------------------------------------------------
    # DOM helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_attached(element, root):
        while element is not None:
            if element is root:
                return True
            element = element.getparent()
        return False

    @staticmethod
    def _unwrap(element):
        """Replace a link by its own content (visible text kept, no href)."""
        element.drop_tag()

    def _replace_with_text(self, element, text):
        tag = "span" if element.tag.lower() in INLINE_TAGS else "p"
        placeholder = html.Element(tag)
        placeholder.text = text
        placeholder.tail = element.tail
        element.getparent().replace(element, placeholder)

    def _neutral_text(self, kind, label):
        factory = self.neutral_texts.get(kind)
        return factory(label) if factory else f"[{label}]"
