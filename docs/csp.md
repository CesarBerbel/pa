# Content-Security-Policy

**Estado: por aplicar.** A política vive no Caddy, em `/etc/caddy/Caddyfile`,
que está no servidor e não neste repositório. Este ficheiro é o que há para
colar lá, mais a explicação de cada linha.

## Porquê

Os cabeçalhos de segurança em produção já estão quase todos: HSTS de um ano com
subdomínios, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` e
`Referrer-Policy`. Falta a CSP — e é a que falta mais, porque o site carrega
JavaScript de cinco origens externas e todas elas correm com acesso total à
página, incluindo ao formulário de marcação, onde a cliente escreve o nome, o
telefone e o email.

Sem CSP, um dia mau de qualquer um desses CDN é um dia mau nosso. Com CSP, um
script que apareça de uma origem não declarada não corre.

## Inventário das origens externas

Levantado dos templates a 24/08/2026. **A auditoria listava quatro origens; são
cinco** — faltava-lhe o `code.jquery.com`, e também o contentor do Google Tag
Manager, que é diferente do Google Analytics.

| Origem | O que traz | Onde |
| --- | --- | --- |
| `cdn.jsdelivr.net` | Bootstrap 5.3.3 (CSS + JS) e Bootstrap Icons 1.11.3 (CSS + tipos de letra) | `templates/base.html` |
| `code.jquery.com` | jQuery 3.7.1 | `public_appointment_form.html`, `public_visual_schedule.html` |
| `www.googletagmanager.com` | `gtag.js` do Analytics (`G-SX6XC4DRZG`) e o `<iframe>` `ns.html` do contentor GTM `GTM-P8N76B5D` | `templates/base.html` |
| `fonts.googleapis.com` / `fonts.gstatic.com` | Google Fonts: Playfair Display, Inter, Allura | `templates/base.html` |
| `elfsightcdn.com` | widget do Instagram, injetado só depois de consentimento funcional | `templates/home.html` |
| `www.google.com` | mapa do rodapé em `<iframe>`, também só após consentimento | `templates/base.html` |
| `lh3.googleusercontent.com` | fotografias de quem escreveu as avaliações do Google | `config/google_reviews.py` |

Duas notas sobre o que não se vê nos templates:

* O `gtag.js` não fala com o `googletagmanager.com` depois de carregado: envia
  as medições para `*.google-analytics.com` e, conforme a região, para
  `region1.google-analytics.com` e `stats.g.doubleclick.net`. Isso é
  `connect-src`, não `script-src`.
* O widget da Elfsight vai buscar código e dados a subdomínios de
  `elfsight.com` e mostra as fotografias do Instagram servidas de
  `*.cdninstagram.com` e `*.fbcdn.net`. É a origem que obriga a política a ser
  mais larga do que se gostaria — e é também a única que se pode retirar sem
  perder nada essencial, se um dia se decidir mostrar as publicações de outra
  maneira.

## O bloco para o Caddyfile

Para colar no bloco do PA — o que faz `reverse_proxy` para `127.0.0.1:8001`.
Vai acompanhado da compressão, que também falta e que está explicada em
[deploy.md](deploy.md).

```caddyfile
# /etc/caddy/Caddyfile
priarantes.com, www.priarantes.com, priarantes.cloud, www.priarantes.cloud {
    encode zstd gzip

    header {
        Content-Security-Policy-Report-Only "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; manifest-src 'self'; worker-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com https://www.googletagmanager.com https://elfsightcdn.com https://*.elfsight.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; img-src 'self' data: https://lh3.googleusercontent.com https://*.googleusercontent.com https://www.googletagmanager.com https://*.google-analytics.com https://*.cdninstagram.com https://*.fbcdn.net https://*.elfsight.com; connect-src 'self' https://*.google-analytics.com https://*.analytics.google.com https://stats.g.doubleclick.net https://*.elfsight.com; frame-src 'self' https://www.google.com https://www.googletagmanager.com https://*.elfsight.com"
    }

    reverse_proxy 127.0.0.1:8001
}
```

## O que cada diretiva faz

* **`default-src 'self'`** — a rede de segurança. Tudo o que não tenha uma
  diretiva própria só pode vir deste domínio. É o que faz a política valer
  também para o que ainda não existe.
* **`base-uri 'self'`** — impede que um `<base>` injetado mude o destino de
  todos os endereços relativos da página de uma vez.
* **`object-src 'none'`** — não há `<object>` nem `<embed>` no site. Fechar o
  que não se usa não custa nada e tira uma via de execução inteira.
* **`frame-ancestors 'none'`** — ninguém nos pode pôr dentro de um `<iframe>`.
  Diz o mesmo que o `X-Frame-Options: DENY` que o Django já envia; os dois
  coexistem, e é este que os browsers modernos leem.
* **`form-action 'self'`** — a submissão do formulário de marcação só pode ir
  para este domínio. Sem isto, um script comprometido mudava o `action` e os
  dados da cliente saíam para outro lado sem nada na página o denunciar.
* **`manifest-src 'self'` e `worker-src 'self'`** — o manifesto e o service
  worker da instalação no ecrã inicial são nossos e só nossos.
* **`script-src`** — as cinco origens do inventário. O `'unsafe-inline'` está
  lá porque tem de estar: ver a secção seguinte.
* **`style-src`** — Bootstrap e Bootstrap Icons do jsDelivr, a folha do Google
  Fonts, e `'unsafe-inline'` por causa dos atributos `style=` espalhados pelos
  templates (o `<iframe>` escondido do GTM é um deles).
* **`font-src`** — os ficheiros de tipo de letra: `fonts.gstatic.com` para o
  Google Fonts e `cdn.jsdelivr.net` para os ícones do Bootstrap, que são uma
  fonte e não imagens. O `data:` cobre as embutidas em CSS.
* **`img-src`** — `data:` para as imagens embutidas, os avatares das avaliações
  do Google, o pixel do Analytics e as fotografias que o widget do Instagram
  traz do `cdninstagram`/`fbcdn`.
* **`connect-src`** — para onde o JavaScript pode falar: as medições do
  Analytics e as chamadas do widget da Elfsight.
* **`frame-src`** — os dois `<iframe>` externos: o mapa do Google no rodapé e o
  `ns.html` do GTM para quem tem o JavaScript desligado.

Não há `report-uri` nem `report-to` porque não há para onde os enviar. O
`Report-Only` sem destino escreve as violações na consola do browser, e é aí
que se vão ler — ver a secção "Como validar".

## O `'unsafe-inline'` nos scripts

É a fraqueza desta política e não se resolve no Caddy. O site tem `<script>`
inline em vários templates — a configuração do `gtag`, o registo do service
worker, o carregador da Elfsight, o consentimento de cookies — e uma CSP sem
`'unsafe-inline'` matava-os a todos.

A forma correta de os manter é um `nonce` por resposta: um valor aleatório que
vai no cabeçalho e em cada `<script>`. Isso obriga o cabeçalho a ser gerado no
Django e não no Caddy, ou seja a instalar uma biblioteca de CSP e a mexer em
todos os templates com script inline. **Fica por decidir**, e não se decide
sozinho: a política no proxy é mais simples de gerir e não custa pedidos ao
Python.

Mesmo com `'unsafe-inline'`, esta política já vale a pena: continua a impedir
que código de uma origem não declarada carregue, que a página seja
enquadrada por outrem e que o formulário submeta para fora.

## Uma nota sobre o `srcdoc`

A pré-visualização de modelos de email, na área interna, mostra o HTML dentro
de um `<iframe srcdoc="…" sandbox="">`. Um `srcdoc` herda a política da página
que o contém, e o `sandbox=""` já impede que qualquer script lá dentro corra.
A CSP não muda nada aqui, mas convém saber porquê quando a pré-visualização
parecer mais pobre do que o email verdadeiro.

## Como aplicar

1. Editar `/etc/caddy/Caddyfile` e acrescentar o bloco `header` acima.
2. Validar: `sudo caddy validate --config /etc/caddy/Caddyfile`
3. Recarregar sem derrubar o outro site: `sudo systemctl reload caddy`
4. Confirmar que o cabeçalho sai:

```bash
curl -sSI https://priarantes.com/ | grep -i content-security-policy
```

## Como validar antes de passar a ativo

Abrir as páginas que carregam mais coisas de fora — a inicial, `/marcar/`,
`/agenda-publica/` — com a consola do browser aberta, e aceitar os cookies para
o widget do Instagram e o mapa também carregarem. Cada violação aparece como
`[Report Only] Refused to load…`.

**Deixar em `Report-Only` durante alguns dias.** Só passa a
`Content-Security-Policy` — sem o `-Report-Only` — depois de vários dias de uso
real sem nenhuma violação nova. Uma origem que só apareça de vez em quando (uma
resposta do Analytics de outra região, uma fotografia servida de outro
subdomínio do Instagram) não se vê num teste de cinco minutos, e em modo ativo
seria uma parte do site a deixar de funcionar sem ninguém perceber porquê.
