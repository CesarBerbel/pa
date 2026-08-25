"""Os indicativos de país, para o telefone poder ser de qualquer sítio.

A clínica é em Coimbra e a maioria dos números é de Portugal, mas quem chega de
férias, quem vive fora e volta, ou quem acompanha um familiar não tem de ter um
número português para poder marcar. O que estava escrito no código aceitava
Portugal e o Brasil, e recusava o resto do mundo com uma mensagem que dizia
exatamente isso.

**O indicativo vem de uma lista e não do que a pessoa escreve.** Escrito à mão,
o mesmo número chegava de cinco maneiras — com `00`, com `+`, com o zero do
trunk à frente — e o WhatsApp não perdoa nenhuma delas. Escolhido numa lista,
só há uma forma de o guardar: E.164, `+` e dígitos, que é o que a Meta e a
Twilio esperam.

Os nomes estão em português porque é a língua da área interna, que é de onde a
maior parte dos cadastros é feita.
"""

from __future__ import annotations

# (código ISO 3166-1 alfa-2, nome, indicativo telefónico)
#
# Os três países de onde vem quase toda a gente ficam no princípio da lista de
# propósito: são os primeiros a aparecer antes de alguém escrever seja o que
# for. O resto sai por ordem alfabética.
DESTAQUES = ["PT", "BR", "ES"]

PAISES = [
    ("AF", "Afeganistão", "93"),
    ("ZA", "África do Sul", "27"),
    ("AL", "Albânia", "355"),
    ("DE", "Alemanha", "49"),
    ("AD", "Andorra", "376"),
    ("AO", "Angola", "244"),
    ("AI", "Anguila", "1264"),
    ("AG", "Antígua e Barbuda", "1268"),
    ("SA", "Arábia Saudita", "966"),
    ("DZ", "Argélia", "213"),
    ("AR", "Argentina", "54"),
    ("AM", "Arménia", "374"),
    ("AW", "Aruba", "297"),
    ("AU", "Austrália", "61"),
    ("AT", "Áustria", "43"),
    ("AZ", "Azerbaijão", "994"),
    ("BS", "Bahamas", "1242"),
    ("BD", "Bangladeche", "880"),
    ("BB", "Barbados", "1246"),
    ("BH", "Barém", "973"),
    ("BE", "Bélgica", "32"),
    ("BZ", "Belize", "501"),
    ("BJ", "Benim", "229"),
    ("BM", "Bermudas", "1441"),
    ("BY", "Bielorrússia", "375"),
    ("BO", "Bolívia", "591"),
    ("BA", "Bósnia e Herzegovina", "387"),
    ("BW", "Botsuana", "267"),
    ("BR", "Brasil", "55"),
    ("BN", "Brunei", "673"),
    ("BG", "Bulgária", "359"),
    ("BF", "Burquina Faso", "226"),
    ("BI", "Burundi", "257"),
    ("BT", "Butão", "975"),
    ("CV", "Cabo Verde", "238"),
    ("CM", "Camarões", "237"),
    ("KH", "Camboja", "855"),
    ("CA", "Canadá", "1"),
    ("QA", "Catar", "974"),
    ("KZ", "Cazaquistão", "7"),
    ("TD", "Chade", "235"),
    ("CL", "Chile", "56"),
    ("CN", "China", "86"),
    ("CY", "Chipre", "357"),
    ("SG", "Cingapura", "65"),
    ("CO", "Colômbia", "57"),
    ("KM", "Comores", "269"),
    ("CG", "Congo", "242"),
    ("CD", "Congo (RDC)", "243"),
    ("KP", "Coreia do Norte", "850"),
    ("KR", "Coreia do Sul", "82"),
    ("CI", "Costa do Marfim", "225"),
    ("CR", "Costa Rica", "506"),
    ("HR", "Croácia", "385"),
    ("CU", "Cuba", "53"),
    ("CW", "Curaçau", "599"),
    ("DK", "Dinamarca", "45"),
    ("DJ", "Djibuti", "253"),
    ("DM", "Domínica", "1767"),
    ("EG", "Egito", "20"),
    ("SV", "El Salvador", "503"),
    ("AE", "Emirados Árabes Unidos", "971"),
    ("EC", "Equador", "593"),
    ("ER", "Eritreia", "291"),
    ("SK", "Eslováquia", "421"),
    ("SI", "Eslovénia", "386"),
    ("ES", "Espanha", "34"),
    ("US", "Estados Unidos", "1"),
    ("EE", "Estónia", "372"),
    ("SZ", "Essuatíni", "268"),
    ("ET", "Etiópia", "251"),
    ("FJ", "Fiji", "679"),
    ("PH", "Filipinas", "63"),
    ("FI", "Finlândia", "358"),
    ("FR", "França", "33"),
    ("GA", "Gabão", "241"),
    ("GM", "Gâmbia", "220"),
    ("GH", "Gana", "233"),
    ("GE", "Geórgia", "995"),
    ("GI", "Gibraltar", "350"),
    ("GD", "Granada", "1473"),
    ("GR", "Grécia", "30"),
    ("GL", "Gronelândia", "299"),
    ("GP", "Guadalupe", "590"),
    ("GU", "Guam", "1671"),
    ("GT", "Guatemala", "502"),
    ("GY", "Guiana", "592"),
    ("GF", "Guiana Francesa", "594"),
    ("GN", "Guiné", "224"),
    ("GQ", "Guiné Equatorial", "240"),
    ("GW", "Guiné-Bissau", "245"),
    ("HT", "Haiti", "509"),
    ("NL", "Holanda", "31"),
    ("HN", "Honduras", "504"),
    ("HK", "Hong Kong", "852"),
    ("HU", "Hungria", "36"),
    ("YE", "Iémen", "967"),
    ("IN", "Índia", "91"),
    ("ID", "Indonésia", "62"),
    ("IQ", "Iraque", "964"),
    ("IR", "Irão", "98"),
    ("IE", "Irlanda", "353"),
    ("IS", "Islândia", "354"),
    ("IL", "Israel", "972"),
    ("IT", "Itália", "39"),
    ("JM", "Jamaica", "1876"),
    ("JP", "Japão", "81"),
    ("JO", "Jordânia", "962"),
    ("KW", "Kuwait", "965"),
    ("LA", "Laos", "856"),
    ("LS", "Lesoto", "266"),
    ("LV", "Letónia", "371"),
    ("LB", "Líbano", "961"),
    ("LR", "Libéria", "231"),
    ("LY", "Líbia", "218"),
    ("LI", "Listenstaine", "423"),
    ("LT", "Lituânia", "370"),
    ("LU", "Luxemburgo", "352"),
    ("MO", "Macau", "853"),
    ("MK", "Macedónia do Norte", "389"),
    ("MG", "Madagáscar", "261"),
    ("MY", "Malásia", "60"),
    ("MW", "Maláui", "265"),
    ("MV", "Maldivas", "960"),
    ("ML", "Mali", "223"),
    ("MT", "Malta", "356"),
    ("MA", "Marrocos", "212"),
    ("MQ", "Martinica", "596"),
    ("MU", "Maurícia", "230"),
    ("MR", "Mauritânia", "222"),
    ("MX", "México", "52"),
    ("MM", "Mianmar", "95"),
    ("MZ", "Moçambique", "258"),
    ("MD", "Moldávia", "373"),
    ("MC", "Mónaco", "377"),
    ("MN", "Mongólia", "976"),
    ("ME", "Montenegro", "382"),
    ("NA", "Namíbia", "264"),
    ("NP", "Nepal", "977"),
    ("NI", "Nicarágua", "505"),
    ("NE", "Níger", "227"),
    ("NG", "Nigéria", "234"),
    ("NO", "Noruega", "47"),
    ("NC", "Nova Caledónia", "687"),
    ("NZ", "Nova Zelândia", "64"),
    ("OM", "Omã", "968"),
    ("PW", "Palau", "680"),
    ("PS", "Palestina", "970"),
    ("PA", "Panamá", "507"),
    ("PG", "Papua-Nova Guiné", "675"),
    ("PK", "Paquistão", "92"),
    ("PY", "Paraguai", "595"),
    ("PE", "Peru", "51"),
    ("PF", "Polinésia Francesa", "689"),
    ("PL", "Polónia", "48"),
    ("PR", "Porto Rico", "1787"),
    ("PT", "Portugal", "351"),
    ("KE", "Quénia", "254"),
    ("KG", "Quirguistão", "996"),
    ("GB", "Reino Unido", "44"),
    ("CF", "República Centro-Africana", "236"),
    ("DO", "República Dominicana", "1809"),
    ("CZ", "República Checa", "420"),
    ("RE", "Reunião", "262"),
    ("RO", "Roménia", "40"),
    ("RW", "Ruanda", "250"),
    ("RU", "Rússia", "7"),
    ("EH", "Saara Ocidental", "212"),
    ("WS", "Samoa", "685"),
    ("AS", "Samoa Americana", "1684"),
    ("SM", "São Marino", "378"),
    ("PM", "São Pedro e Miquelão", "508"),
    ("ST", "São Tomé e Príncipe", "239"),
    ("VC", "São Vicente e Granadinas", "1784"),
    ("SH", "Santa Helena", "290"),
    ("LC", "Santa Lúcia", "1758"),
    ("KN", "São Cristóvão e Neves", "1869"),
    ("SN", "Senegal", "221"),
    ("SL", "Serra Leoa", "232"),
    ("RS", "Sérvia", "381"),
    ("SC", "Seicheles", "248"),
    ("SY", "Síria", "963"),
    ("SO", "Somália", "252"),
    ("LK", "Sri Lanca", "94"),
    ("SD", "Sudão", "249"),
    ("SS", "Sudão do Sul", "211"),
    ("SE", "Suécia", "46"),
    ("CH", "Suíça", "41"),
    ("SR", "Suriname", "597"),
    ("TH", "Tailândia", "66"),
    ("TW", "Taiwan", "886"),
    ("TJ", "Tajiquistão", "992"),
    ("TZ", "Tanzânia", "255"),
    ("TL", "Timor-Leste", "670"),
    ("TG", "Togo", "228"),
    ("TO", "Tonga", "676"),
    ("TT", "Trindade e Tobago", "1868"),
    ("TN", "Tunísia", "216"),
    ("TC", "Turcas e Caicos", "1649"),
    ("TM", "Turquemenistão", "993"),
    ("TR", "Turquia", "90"),
    ("UA", "Ucrânia", "380"),
    ("UG", "Uganda", "256"),
    ("UY", "Uruguai", "598"),
    ("UZ", "Usbequistão", "998"),
    ("VU", "Vanuatu", "678"),
    ("VA", "Vaticano", "379"),
    ("VE", "Venezuela", "58"),
    ("VN", "Vietname", "84"),
    ("VG", "Virgens Britânicas", "1284"),
    ("VI", "Virgens Americanas", "1340"),
    ("ZM", "Zâmbia", "260"),
    ("ZW", "Zimbábue", "263"),
]

POR_CODIGO = {iso: (nome, indicativo) for iso, nome, indicativo in PAISES}

# O que o país por omissão vale quando um número chega sem indicativo nenhum.
PAIS_POR_OMISSAO = "PT"

# Há indicativos partilhados por vários países, e sem olhar para o prefixo
# regional — que muda com o tempo — não há como saber qual deles é. Estes são
# os que se assumem: os outros ficam escritos no número, que é o que conta.
PRINCIPAIS_POR_INDICATIVO = {
    "1": "US",
    "7": "RU",
    "212": "MA",
}


def ordenados():
    """A lista como ela é mostrada: os habituais primeiro, o resto por nome."""

    destaques = [(iso, *POR_CODIGO[iso]) for iso in DESTAQUES if iso in POR_CODIGO]
    restantes = sorted(
        (entrada for entrada in PAISES if entrada[0] not in DESTAQUES),
        key=lambda entrada: entrada[1],
    )

    return destaques + restantes


def indicativo(iso):
    """O indicativo deste país, ou o de Portugal se o código não existir."""

    nome_e_indicativo = POR_CODIGO.get((iso or "").upper())

    if not nome_e_indicativo:
        return POR_CODIGO[PAIS_POR_OMISSAO][1]

    return nome_e_indicativo[1]


def separar(numero):
    """Parte um número E.164 em (país, resto), para o formulário o mostrar.

    Faz-se pelo indicativo mais comprido que encaixe: `+1268` é Antígua e
    `+1` são os Estados Unidos, e o mais curto engolia o outro.

    Os países que partilham indicativo — o Canadá e os Estados Unidos, os dois
    com `+1`, ou a Rússia e o Cazaquistão com `+7` — não se distinguem sem
    olhar para o prefixo regional, que muda com o tempo. Sai o que estiver em
    `PRINCIPAIS_POR_INDICATIVO`: o que fica guardado é o número inteiro, e é
    esse que importa.
    """

    numero = (numero or "").strip()

    if not numero.startswith("+"):
        return "", numero

    digitos = numero[1:]

    for tamanho in (4, 3, 2, 1):
        prefixo = digitos[:tamanho]

        if prefixo in PRINCIPAIS_POR_INDICATIVO:
            return PRINCIPAIS_POR_INDICATIVO[prefixo], digitos[tamanho:]

        for iso, _nome, codigo in PAISES:
            if codigo == prefixo:
                return iso, digitos[tamanho:]

    return "", digitos
