from urllib.parse import quote, urljoin

from django.conf import settings
from django.urls import translate_url

from appointments.models import TreatedCondition
from config.maps import endereco_do_mapa
from notifications.models import BeforeAfterCase


def _format_pt_phone(phone):
    """Formats a +351XXXXXXXXX number as '+351 XXX XXX XXX' for display."""

    digits = phone.lstrip("+")

    if digits.startswith("351") and len(digits) == 12:
        return f"+351 {digits[3:6]} {digits[6:9]} {digits[9:12]}"

    return phone


def seo_settings(request):
    """Expose site-wide SEO settings to templates."""

    site_url = settings.SITE_URL.rstrip("/")
    current_path = request.path or "/"

    whatsapp_number = settings.SEO_WHATSAPP_NUMBER
    whatsapp_digits = whatsapp_number.lstrip("+")
    whatsapp_message = quote("Olá, gostaria de mais informações.")

    return {
        "SEO_SITE_URL": site_url,
        "SEO_SITE_NAME": settings.SEO_SITE_NAME,
        "SEO_DEFAULT_TITLE": settings.SEO_DEFAULT_TITLE,
        "SEO_DEFAULT_DESCRIPTION": settings.SEO_DEFAULT_DESCRIPTION,
        "SEO_DEFAULT_KEYWORDS": settings.SEO_DEFAULT_KEYWORDS,
        "SEO_DEFAULT_IMAGE_URL": urljoin(
            site_url + "/", settings.SEO_DEFAULT_IMAGE_PATH.lstrip("/")
        ),
        "SEO_CURRENT_URL": urljoin(site_url + "/", current_path.lstrip("/")),
        "SEO_LOCALE": settings.SEO_LOCALE,
        "SEO_THEME_COLOR": settings.SEO_THEME_COLOR,
        "SEO_ROBOTS_DEFAULT": settings.SEO_ROBOTS_DEFAULT,
        "SEO_WHATSAPP_NUMBER": whatsapp_number,
        "SEO_WHATSAPP_DISPLAY": _format_pt_phone(whatsapp_number),
        "SEO_WHATSAPP_LINK": f"https://wa.me/{whatsapp_digits}?text={whatsapp_message}",
    }


def map_settings(request):
    """O endereço do mapa do rodapé.

    Um context processor porque o rodapé é do `base.html` e aparece em todas as
    páginas: passá-lo view a view era repetir a mesma linha dezenas de vezes e
    esquecê-la numa.
    """

    from django.utils import translation

    return {
        "GOOGLE_MAP_EMBED_URL": endereco_do_mapa(translation.get_language()),
    }


def instagram_settings(request):
    """Expose the Instagram profile link to templates."""

    return {
        "INSTAGRAM_PROFILE_URL": settings.INSTAGRAM_PROFILE_URL,
    }


def clinical_settings(request):
    """Expõe o prazo de conservação dos registos clínicos.

    Zero significa "por definir": a ficha avisa e a política de privacidade
    omite o prazo, para não publicar um compromisso que não foi assumido.
    """

    return {
        "clinical_retention_years": settings.CLINICAL_RECORD_RETENTION_YEARS,
    }


def language_alternates(request):
    """Expose the current page in every language, for hreflang tags.

    translate_url() returns the path unchanged when it cannot be resolved, so
    pages outside i18n_patterns (admin, robots.txt) degrade harmlessly.
    """

    site_url = settings.SITE_URL.rstrip("/")
    current_path = request.get_full_path()

    alternates = []

    for code, name in settings.LANGUAGES:
        translated_path = translate_url(current_path, code)

        alternates.append(
            {
                "code": code,
                "name": name,
                "path": translated_path,
                "url": urljoin(site_url + "/", translated_path.lstrip("/")),
            }
        )

    return {"LANGUAGE_ALTERNATES": alternates}


def before_after_gallery(request):
    """Diz se há alguma comparação publicada.

    A entrada de menu e a ligação do rodapé só existem quando há o que
    mostrar: uma página vazia é um beco, e um menu que leva a lado nenhum
    ensina as pessoas a não clicar no menu.

    É uma consulta `EXISTS` por página. Podia ser guardada em cache, mas
    guardá-la traz um problema pior: o valor teria de ser esquecido a cada
    caso criado, apagado ou escondido, e um esquecimento falhado deixaria o
    menu a mentir durante horas. Numa tabela desta dimensão a consulta não se
    mede.
    """

    return {
        "HAS_BEFORE_AFTER": BeforeAfterCase.objects.filter(is_active=True).exists(),
    }


def treated_conditions(request):
    """Onde fica a página de cada problema publicado, para quem lhe queira ligar.

    Os cards da página inicial existiam antes destas páginas e não vão deixar
    de existir: têm o ícone, o texto escrito à mão e a tradução inglesa no
    catálogo. O que lhes falta é o passo seguinte, e é isto que lho dá — mas
    só para os que já estão publicados. Um card a ligar para um rascunho
    seria um 404 na página mais visitada do site.

    **As chaves vêm com underscores e não com hífens.** A linguagem de
    templates do Django não sabe indexar um dicionário por uma chave com
    hífen — `{{ d.unha-encravada }}` é lido como uma subtração. Trocar o
    caráter aqui evita um filtro novo só para isto.

    `HAS_TREATED_CONDITIONS` é o mesmo dicionário visto como sim ou não, para
    a ligação do rodapé aparecer sozinha quando a primeira for publicada.
    """

    ligacoes = {
        condicao.slug.replace("-", "_"): condicao.get_absolute_url()
        for condicao in TreatedCondition.objects.filter(is_published=True)
    }

    return {
        "CONDITION_LINKS": ligacoes,
        "HAS_TREATED_CONDITIONS": bool(ligacoes),
    }


def opening_hours(request):
    """O horário de funcionamento para o rodapé.

    Mesma fonte que a agenda e que os dados estruturados: os `BusinessHour`.
    O rodapé tinha o horário escrito à mão e ficava a mentir sempre que a
    profissional o mudava na área interna.
    """

    from appointments.opening_hours import opening_hours as horario

    return {"OPENING_HOURS": horario()}
