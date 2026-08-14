// Service worker da Priscila Arantes PA.
//
// Estratégia deliberada: páginas nunca ficam em cache.
//
// Numa agenda, servir uma página guardada mostraria horários que entretanto já
// foram ocupados — e alguém tentaria marcar um que já não existe. Por isso os
// documentos vão sempre à rede, e só falham para a página offline. Apenas os
// ficheiros estáticos são guardados, porque não mudam entre pedidos.

const CACHE_NAME = "pa-static-{{ cache_version }}";
const OFFLINE_URL = "{{ offline_url }}";

const PRECACHE = [
    OFFLINE_URL,
    {% for url in precache_urls %}"{{ url }}",
    {% endfor %}
];

self.addEventListener("install", function (event) {
    event.waitUntil(
        caches
            .open(CACHE_NAME)
            .then(function (cache) {
                return cache.addAll(PRECACHE);
            })
            // Um ficheiro em falta não pode impedir a instalação: sem isto, a
            // PWA deixaria de funcionar por causa de um recurso secundário.
            .catch(function () {})
            .then(function () {
                return self.skipWaiting();
            })
    );
});

self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches
            .keys()
            .then(function (nomes) {
                return Promise.all(
                    nomes
                        .filter(function (nome) {
                            return nome.startsWith("pa-static-") && nome !== CACHE_NAME;
                        })
                        .map(function (nome) {
                            return caches.delete(nome);
                        })
                );
            })
            .then(function () {
                return self.clients.claim();
            })
    );
});

self.addEventListener("fetch", function (event) {
    const request = event.request;

    if (request.method !== "GET") {
        return;
    }

    const url = new URL(request.url);

    // Pedidos a outros domínios (mapas, fontes, CDN) seguem sem interferência.
    if (url.origin !== self.location.origin) {
        return;
    }

    // Documentos: sempre da rede. Sem rede, a página offline.
    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).catch(function () {
                return caches.match(OFFLINE_URL);
            })
        );
        return;
    }

    // Estáticos: da cache primeiro, por serem imutáveis entre pedidos.
    if (url.pathname.startsWith("/static/")) {
        event.respondWith(
            caches.match(request).then(function (guardado) {
                if (guardado) {
                    return guardado;
                }

                return fetch(request).then(function (response) {
                    if (response.ok) {
                        const copia = response.clone();
                        caches.open(CACHE_NAME).then(function (cache) {
                            cache.put(request, copia);
                        });
                    }

                    return response;
                });
            })
        );
    }
});
