from __future__ import annotations

from appointments.models import get_localized_value

# A homepage mostra uma grelha de 4 colunas. O catálogo real tem cinco
# categorias, por isso Manicure e Pedicure — que partilham o mesmo tipo de
# cuidado estético — aparecem juntas num único card. O agrupamento é apenas
# de apresentação: as categorias continuam separadas na marcação e no SEO.
MERGED_CARDS = [
    {
        "slugs": ("manicure", "pedicure"),
        "name": "Manicure e Pedicure",
        "name_en": "Manicure and Pedicure",
        "description": (
            "Cuidados estéticos e técnicos para mãos, pés e unhas."
        ),
        "description_en": (
            "Aesthetic and technical care for hands, feet and nails."
        ),
    },
]


class ServiceCard:
    # Objeto simples de apresentação consumido por home.html. Serve tanto uma
    # categoria isolada como um grupo de categorias fundidas.

    def __init__(self, categories, name=None, name_en=None, description=None, description_en=None):
        self.categories = list(categories)
        self._name = name
        self._name_en = name_en
        self._description = description
        self._description_en = description_en

    @property
    def display_name(self):
        if self._name:
            return get_localized_value(self._name, self._name_en or "")

        return self.categories[0].display_name

    @property
    def display_description(self):
        if self._description:
            return get_localized_value(self._description, self._description_en or "")

        return self.categories[0].display_description

    @property
    def is_coming_soon(self):
        # Só marcamos "em breve" quando nenhuma das categorias do card já aceita
        # marcações, senão escondíamos serviços que estão mesmo disponíveis.
        return all(category.is_coming_soon for category in self.categories)

    @property
    def show_prices(self):
        return all(category.show_prices for category in self.categories)

    @property
    def services(self):
        # Intercala os serviços das categorias fundidas para que o teaser não
        # fique só com os da primeira depois do corte feito no template.
        lists = [list(category.services.all()) for category in self.categories]
        merged = []

        for index in range(max((len(items) for items in lists), default=0)):
            for items in lists:
                if index < len(items):
                    merged.append(items[index])

        return merged


def build_home_service_cards(categories):
    # Converte as categorias ativas nos cards da homepage, fundindo os grupos
    # definidos em MERGED_CARDS e preservando a ordem de exibição original.
    categories = list(categories)
    by_slug = {category.slug: category for category in categories}

    grouped_slugs = {}

    for card in MERGED_CARDS:
        present = [slug for slug in card["slugs"] if slug in by_slug]

        # Um grupo com uma categoria só não precisa de card fundido.
        if len(present) < 2:
            continue

        for slug in present:
            grouped_slugs[slug] = card

    cards = []
    emitted = set()

    for category in categories:
        card = grouped_slugs.get(category.slug)

        if card is None:
            cards.append(ServiceCard([category]))
            continue

        if id(card) in emitted:
            continue

        emitted.add(id(card))
        cards.append(
            ServiceCard(
                [by_slug[slug] for slug in card["slugs"] if slug in by_slug],
                name=card["name"],
                name_en=card["name_en"],
                description=card["description"],
                description_en=card["description_en"],
            )
        )

    return cards
