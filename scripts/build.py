# -*- coding: utf-8 -*-
"""Rebuild the Kolizey site from the saved menu pages."""

import re
from html import escape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent / "source"
IMG = "https://kolizey-pizza.com/img/"
ORDER = ["sobranecka", "vokzal", "artema", "rosvyhovo"]
APP_STORE = "https://apps.apple.com/ua/app/%D0%BF%D1%96%D1%86%D0%B5%D1%80%D1%96%D1%8F-%D0%BA%D0%B0%D1%84%D0%B5-%D0%BA%D0%BE%D0%BB%D1%96%D0%B7%D0%B5%D0%B9/id1487062703?l=ua"
PLAY = "https://play.google.com/store/apps/details?id=com.devseonet.coliseum"

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class Node:
    def __init__(self, tag, attrs, data=""):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []
        self.data = data

    def classes(self):
        return (self.attrs.get("class") or "").split()

    def has(self, name):
        return name in self.classes()

    def find(self, pred):
        if self.tag and pred(self):
            return self
        for child in self.children:
            found = child.find(pred)
            if found:
                return found
        return None

    def find_all(self, pred):
        found = []
        if self.tag and pred(self):
            found.append(self)
        for child in self.children:
            found.extend(child.find_all(pred))
        return found


class Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document", [])
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.stack[-1].children.append(Node("", {}, " "))
            return
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(Node("", {}, data))


def text_of(node):
    if node is None:
        return ""
    parts = []

    def walk(current):
        if not current.tag:
            parts.append(current.data)
            return
        for child in current.children:
            walk(child)

    walk(node)
    return re.sub(r"\s+", " ", "".join(parts)).replace("\xa0", " ").strip()


def polish(value):
    value = re.sub(r"\s+", " ", value or "").strip()
    parts = re.split(r"(«[^»]*»|“[^”]*”|\"[^\"]*\")", value)
    cleaned = []
    for index, part in enumerate(parts):
        if index % 2 == 1:
            cleaned.append(part)
            continue
        words = []
        for word in part.split(" "):
            letters = [char for char in word if char.isalpha()]
            if len(letters) >= 3 and all(char.isupper() for char in letters):
                word = word.lower()
            words.append(word)
        cleaned.append(" ".join(words))
    value = "".join(cleaned)
    if value and value[0].isalpha() and value[0].islower():
        value = value[0].upper() + value[1:]
    return value


def tidy_amount(value):
    value = re.sub(r"\s+", " ", value or "").strip()
    value = re.sub(r"\bграм(и|ів|а)?\b", "г", value, flags=re.IGNORECASE)
    return value


def pretty_street(value):
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^[мm]\.\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<!,)\s+(?=\d)", ", ", value)
    value = re.sub(r"(\d)\s+([A-Za-zА-Яа-яІіЇїЄєҐґ])", "\\1\u00a0\\2", value)
    return value


def pretty_hours(value):
    value = value.replace(" - ", "–").replace("-", "–")
    value = re.sub(r"\s+", " ", value).strip()
    return value.replace(" ", " · ", 1)


def tel_href(phone):
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("380"):
        return "tel:+" + digits
    if digits.startswith("0"):
        return "tel:+38" + digits
    return "tel:+" + digits


def img_url(src):
    src = src.replace("\\", "/").lstrip()
    src = re.sub(r"^(\.\./)+", "", src)
    if src.startswith("img/"):
        src = src[4:]
    return IMG + src


def e(value):
    return escape(value or "", quote=True)


def price_html(price):
    match = re.fullmatch(r"(.+?)\s*грн\.?", price.strip())
    if match:
        return f'<span class="price">{e(match.group(1))}<small> грн</small></span>'
    return f'<span class="price">{e(price)}</span>'


def offers_html(portions):
    chunks = []
    for portion in portions:
        amount = f'<span class="amt">{e(portion["amount"])}</span>' if portion["amount"] else ""
        price = price_html(portion["price"]) if portion["price"] else ""
        if amount or price:
            chunks.append(f'<div class="offer">{amount}{price}</div>')
    if not chunks:
        return ""
    return f'<div class="offers">{"".join(chunks)}</div>'


def parse_file(path):
    parser = Builder()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    root = parser.root

    def is_title(node):
        return node.tag == "h2" and any(
            name in node.classes()
            for name in ("card__title", "drinks__title", "goods__title", "extras__title")
        )

    def link(node):
        for child in node.children:
            child.parent = node
            link(child)

    link(root)

    box_names = ("card__items", "drinks__lists", "goods__lists", "extras__lists")
    parsed_categories = []
    for title_node in root.find_all(is_title):
        section = title_node.parent
        boxes = section.find_all(lambda node: any(name in node.classes() for name in box_names))
        if not boxes:
            continue
        kind = "cards" if any(box.has("card__items") for box in boxes) else "list"
        groups = []
        current = {"title": "", "items": []}
        groups.append(current)
        for listbox in boxes:
            for child in listbox.children:
                if not child.tag:
                    continue
                if child.has("drinks__trademark"):
                    current = {"title": polish(text_of(child)), "items": []}
                    groups.append(current)
                    continue
                if kind == "cards" and child.has("card__item"):
                    current["items"].append(parse_card(child))
                elif kind == "list" and "list" in child.classes():
                    current["items"].append(parse_row(child))
        groups = [group for group in groups if group["items"]]
        if groups:
            parsed_categories.append({
                "title": polish(text_of(title_node)),
                "kind": kind,
                "groups": groups,
            })

    footer = root.find(lambda node: node.tag == "footer")
    address = label_text(footer, "address__city")
    city, street = split_address(address)
    hours = pretty_hours(label_text(footer, "address__time"))
    phone = label_text(footer, "address__phone")
    delivery = text_of(footer.find(lambda node: node.has("delivery__title"))) if footer else ""
    iframe = footer.find(lambda node: node.tag == "iframe") if footer else None
    social = {}
    apps = {}
    if footer:
        for link_node in footer.find_all(lambda node: node.tag == "a" and node.attrs.get("href")):
            href = link_node.attrs["href"]
            if "instagram.com" in href:
                social["instagram"] = href
            elif "facebook.com" in href:
                social["facebook"] = href
            elif "apps.apple.com" in href:
                apps["app_store"] = href
            elif "play.google.com" in href:
                apps["play"] = href

    return {
        "city": city,
        "street": street,
        "address": address,
        "hours": hours,
        "phone": phone,
        "delivery": polish(delivery) if delivery.isupper() else delivery,
        "map": iframe.attrs.get("src", "") if iframe else "",
        "social": social,
        "apps": apps,
        "categories": parsed_categories,
    }


def label_text(footer, class_name):
    if footer is None:
        return ""
    node = footer.find(lambda item: item.has(class_name))
    value = text_of(node)
    if ":" in value:
        value = value.split(":", 1)[1].strip()
    return value


def split_address(address):
    parts = [part.strip() for part in address.split(",", 1)]
    city = pretty_street(parts[0]) if parts else ""
    city = re.sub(r"^м\.\s*", "", city, flags=re.IGNORECASE)
    street = pretty_street(parts[1]) if len(parts) > 1 else pretty_street(address)
    return city, street


def portions_of(node):
    portions = []
    bodies = node.find_all(
        lambda item: "list__body" in item.classes() or "portion" in item.classes()
    )
    for body in bodies:
        amount_node = body.find(lambda item: item.has("portion__weight") or item.has("list__amount"))
        price_node = body.find(lambda item: item.has("portion__price") or item.has("list__price"))
        amount = tidy_amount(text_of(amount_node))
        price = text_of(price_node)
        if amount or price:
            portions.append({"amount": amount, "price": price})
    return portions


def parse_card(node):
    image = node.find(lambda item: item.tag == "img")
    name = polish(text_of(node.find(lambda item: item.has("card__name"))))
    note = text_of(node.find(lambda item: item.has("card__ingredient")))
    return {
        "name": name,
        "note": note,
        "image": img_url(image.attrs["src"]) if image and image.attrs.get("src") else "",
        "portions": portions_of(node),
    }


def parse_row(node):
    name = polish(text_of(node.find(lambda item: item.has("list__ukr-name"))))
    notes = [text_of(item) for item in node.find_all(lambda item: item.has("list__sort"))]
    note = " · ".join(item for item in notes if item)
    return {
        "name": name,
        "note": note,
        "image": "",
        "portions": portions_of(node),
    }


def search_blob(item):
    return re.sub(r"\s+", " ", f'{item["name"]} {item["note"]}'.lower()).strip()


def render_item(item, plain=False):
    photo = ""
    if item["image"]:
        photo = (
            f'<div class="photo"><img src="{e(item["image"])}" alt="{e(item["name"])}" width="148" height="148" '
            f'loading="lazy" decoding="async" onerror="this.parentElement.classList.add(\'is-off\')"></div>'
        )
    klass = "dish dish--plain" if plain or not photo else "dish"
    note = f'<p>{e(item["note"])}</p>' if item["note"] else ""
    heading = "h3" if klass.startswith("dish") else "h4"
    return (
        f'<article class="{klass}" data-q="{e(search_blob(item))}">'
        f"{photo}<div><{heading}>{e(item['name'])}</{heading}>{note}</div>"
        f"{offers_html(item['portions'])}</article>"
    )


def render_row(item):
    note = f'<p>{e(item["note"])}</p>' if item["note"] else ""
    return (
        f'<article class="row" data-q="{e(search_blob(item))}">'
        f"<div><h4>{e(item['name'])}</h4>{note}</div>"
        f"{offers_html(item['portions'])}</article>"
    )


ARROW = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'

HEAD_LINKS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Roboto+Serif:opsz,wght@8..144,400;8..144,500;8..144,600;8..144,700&display=swap" rel="stylesheet">
<link rel="icon" href="{favicon}">
"""

ANALYTICS = """
<script async src="https://www.googletagmanager.com/gtag/js?id=G-NY5XQ41CEL"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-NY5XQ41CEL');
</script>
"""


def page_start(title, description, depth, extra=""):
    favicon = "../" * depth + "favicon.png"
    css = "../" * depth + "assets/style.css?v=11"
    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<meta name="theme-color" content="#f4f0e8">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:image" content="https://kolizey-pizza.com/img/pizza/Monaco.jpg">
{HEAD_LINKS.format(favicon=favicon)}
<link rel="stylesheet" href="{css}">
{ANALYTICS}
</head>
<body>
<a class="skip" href="#{extra or 'places'}">До вмісту</a>
"""


def render_home(locations):
    places = []
    for index, (slug, place) in enumerate(locations, start=1):
        places.append(f"""
<li class="place">
  <span class="place__n">{index:02d}</span>
  <div>
    <span class="place__city">{e(place['city'])}</span>
    <h2 class="place__street">{e(place['street'])}</h2>
    <p class="place__meta">{e(place['hours'])}</p>
  </div>
  <div class="place__actions">
    <a class="btn btn-ghost" href="{e(tel_href(place['phone']))}">{e(place['phone'])}</a>
    <a class="btn btn-solid" href="{slug}/">Меню</a>
  </div>
</li>""")
    html = page_start(
        "Піцерія-кафе «Колізей»",
        "Піцерія-кафе «Колізей» в Ужгороді та Мукачеві. Меню, години роботи, телефони і доставка.",
        0,
    )
    html += f"""
<header class="wrap site-header">
  <a class="brand" href="./"><i></i>Колізей</a>
  <span class="header-note">Ужгород · Мукачево</span>
</header>
<main class="wrap">
  <section class="hero">
    <div>
      <p class="eyebrow">Піцерія-кафе</p>
      <h1>Колізей</h1>
      <p class="lede">Чотири заклади в Ужгороді та Мукачеві. Оберіть адресу — меню, телефон і доставка відкриються одразу.</p>
    </div>
    <img class="hero-photo" src="assets/hero.jpg" alt="Піца Монако" width="840" height="840">
  </section>
  <p class="places-label" id="places">Заклади</p>
  <ul class="places">
    {''.join(places)}
  </ul>
</main>
<footer class="wrap home-foot">
  <p>Доставка містом і районом — телефоном або в застосунку.</p>
  <p><a href="{APP_STORE}">App Store</a> · <a href="{PLAY}">Google Play</a><br>© 2026 Піцерія-кафе «Колізей»</p>
</footer>
</body>
</html>
"""
    return html


def render_menu(slug, place, locations):
    cats = []
    blocks = []
    for index, category in enumerate(place["categories"]):
        cid = f"c{index}"
        count = sum(len(group["items"]) for group in category["groups"])
        cats.append(f'<a href="#{cid}">{e(category["title"])}</a>')
        body = []
        for group in category["groups"]:
            if category["kind"] == "cards":
                items = "".join(
                    render_item(item, plain=not item["image"]) for item in group["items"]
                )
                inner = f'<div class="dishes">{items}</div>'
            else:
                items = "".join(render_row(item) for item in group["items"])
                heading = f'<h3>{e(group["title"])}</h3>' if group["title"] else ""
                inner = f'<div class="group">{heading}<div class="rows">{items}</div></div>'
            body.append(inner)
        blocks.append(f"""
<section class="block" id="{cid}">
  <div class="block__head"><h2>{e(category["title"])}</h2><span>{count}</span></div>
  {''.join(body)}
</section>""")

    others = []
    for other_slug, other in locations:
        if other_slug == slug:
            continue
        others.append(f'<a href="../{other_slug}/">{e(other["city"])}, {e(other["street"])}</a>')

    social = []
    if place["social"].get("instagram"):
        social.append(f'<a href="{e(place["social"]["instagram"])}">Instagram</a>')
    if place["social"].get("facebook"):
        social.append(f'<a href="{e(place["social"]["facebook"])}">Facebook</a>')
    social.append(f'<a href="{e(place["apps"].get("app_store") or APP_STORE)}">App Store</a>')
    social.append(f'<a href="{e(place["apps"].get("play") or PLAY)}">Google Play</a>')

    title = f'{place["street"]} — Колізей'
    description = f'Меню піцерії-кафе «Колізей», {place["city"]}, {place["street"]}. {place["hours"]}.'
    html = page_start(title, description, 1, "c0")
    html += f"""
<header class="top">
  <div class="wrap top__row">
    <a class="back" href="../">{ARROW}<span>Усі заклади</span></a>
    <div class="loc">
      <strong>{e(place["street"])}</strong>
      <span>{e(place["city"])} · {e(place["hours"])}</span>
    </div>
    <input class="search" type="search" placeholder="Пошук страви" aria-label="Пошук страви" autocomplete="off">
    <a class="btn btn-solid call" href="{e(tel_href(place["phone"]))}"><span>{e(place["phone"])}</span></a>
  </div>
  <div class="wrap">
    <nav class="cats" aria-label="Розділи меню">{''.join(cats)}</nav>
  </div>
</header>
<main class="wrap menu-main">
  {''.join(blocks)}
  <p class="empty" hidden>Нічого не знайшлося. Спробуйте іншу назву.</p>
</main>
<footer class="wrap site-foot">
  <div class="foot-grid">
    <div>
      <h2>Контакти</h2>
      <p>{e(place["city"])}, {e(place["street"])}</p>
      <p class="contact-line">{e(place["hours"])}</p>
      <p class="contact-line">{e(place["delivery"])}</p>
      <a class="phone-link" href="{e(tel_href(place["phone"]))}">{e(place["phone"])}</a>
    </div>
    <div class="foot-links">{''.join(social)}</div>
  </div>
  <iframe class="map" title="Карта: {e(place["street"])}" src="{e(place["map"])}" loading="lazy" referrerpolicy="no-referrer-when-downgrade" allowfullscreen></iframe>
  <p class="other">Інші заклади: {' · '.join(others)}</p>
  <p class="copy">© 2026 Піцерія-кафе «Колізей»</p>
</footer>
<script src="../assets/menu.js"></script>
</body>
</html>
"""
    return html


def main():
    locations = []
    for slug in ORDER:
        place = parse_file(SOURCE / f"{slug}.html")
        locations.append((slug, place))
        counts = ", ".join(
            f'{category["title"]} {sum(len(group["items"]) for group in category["groups"])}'
            for category in place["categories"]
        )
        print(f"{slug}: {place['city']} / {place['street']} / {place['phone']}")
        print("  " + counts)

    (ROOT / "index.html").write_text(render_home(locations), encoding="utf-8")
    for slug, place in locations:
        folder = ROOT / slug
        folder.mkdir(exist_ok=True)
        (folder / "index.html").write_text(render_menu(slug, place, locations), encoding="utf-8")
    print("wrote pages")


if __name__ == "__main__":
    main()
