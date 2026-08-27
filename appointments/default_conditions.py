"""Os problemas que a pedicure terapêutica trata, com a página de cada um.

Isto é o texto de partida, não o texto final. Quem procura ajuda no Google
escreve o que sente — "unha encravada dói muito", "micose na unha do pé
tratamento" — e não o nome do serviço que resolve isso. Cada entrada aqui é
uma página que responde à pergunta que a pessoa fez.

**Nasce por publicar, de propósito.** São afirmações sobre saúde num site
assinado por uma enfermeira: o que está escrito abaixo é informação geral,
redigida com cuidado mas por quem não examinou ninguém. Nenhuma destas páginas
aparece no site enquanto a profissional não a ler e ligar o interruptor.

O `slug` é o endereço e não muda depois de a página estar indexada: mudá-lo é
começar do zero aos olhos do Google. Escolhem-se aqui pelas palavras que as
pessoas escrevem, e não pelo nome clínico — `unha-encravada` e não
`onicocriptose`, que é o que ninguém procura.
"""

CONDICOES = [
    {
        "slug": "unha-encravada",
        "name": "Unha encravada",
        "display_order": 10,
        "meta_title": "Unha encravada: tratamento em Coimbra",
        "meta_description": (
            "A unha encravada trata-se sem esperar que infecte. Veja porque "
            "acontece, os sinais de alerta e como é feito o tratamento em "
            "Coimbra."
        ),
        "keywords": (
            "unha encravada, unha encravada tratamento, onicocriptose, "
            "unha encravada Coimbra, unha do pé encravada, unha encravada infecionada"
        ),
        "summary": (
            "Quando o canto da unha entra na pele em vez de crescer por cima "
            "dela, o dedo dói ao mais pequeno toque — e um sapato fechado "
            "chega para tornar o dia difícil. Trata-se, e quanto mais cedo "
            "menos dói."
        ),
        "what_it_is": (
            "A unha encravada, ou onicocriptose, é o bordo da unha a crescer "
            "para dentro da pele que a rodeia em vez de deslizar por cima "
            "dela. A pele responde como responderia a qualquer corpo "
            "estranho: incha, fica vermelha e dói. Acontece quase sempre no "
            "dedo grande do pé, e quase sempre de um lado só."
        ),
        "why_it_happens": (
            "As causas repetem-se: unhas cortadas em curva ou cortadas "
            "demasiado curtas, sapatos que apertam à frente, um traumatismo "
            "antigo que mudou a forma da unha, ou simplesmente uma unha "
            "naturalmente mais curva do que a média. A transpiração ajuda — "
            "a pele húmida é mais mole e deixa-se penetrar mais facilmente."
        ),
        "warning_signs": (
            "Dor ao calçar, ao andar ou ao encostar o lençol. Vermelhidão e "
            "inchaço no canto do dedo. Pele a crescer por cima da unha. "
            "Líquido, pus ou mau cheiro. Se houver pus, febre, ou se a "
            "pessoa tiver diabetes ou má circulação, isto deixa de poder "
            "esperar: deve ser visto sem demora."
        ),
        "how_we_treat": (
            "A consulta começa por perceber há quanto tempo dura e o que já "
            "foi tentado. O procedimento habitual é libertar o bordo da unha "
            "que está a penetrar a pele e remover a espícula responsável, "
            "com material esterilizado. Quando o problema é a forma da unha "
            "e não um episódio isolado, pode propor-se uma órtese ungueal — "
            "uma peça colocada na unha que a vai corrigindo ao longo de "
            "semanas, sem cirurgia. A maior parte das pessoas sai a andar "
            "com muito menos dor do que entrou."
        ),
        "home_care": (
            "Corte a unha a direito e não em curva, e não a corte rente aos "
            "cantos. Escolha calçado que não aperte à frente. Mantenha o pé "
            "seco, sobretudo entre os dedos. E não tente desencravar a unha "
            "com objetos em casa: é assim que a maioria das infeções começa."
        ),
        "questions": [
            {
                "question": "O tratamento da unha encravada dói?",
                "answer": (
                    "O que dói é a unha encravada. O procedimento é feito com "
                    "cuidado e a maior parte das pessoas descreve alívio "
                    "imediato depois de a espícula sair. Diga sempre o que "
                    "está a sentir durante a consulta — o ritmo ajusta-se a "
                    "si."
                ),
            },
            {
                "question": "Preciso de cirurgia para tratar uma unha encravada?",
                "answer": (
                    "Na maioria dos casos não. O tratamento conservador — "
                    "libertar o bordo e, se a forma da unha o justificar, "
                    "colocar uma órtese — resolve grande parte das "
                    "situações. A cirurgia é uma decisão médica, para casos "
                    "que não respondem ou que reincidem sempre."
                ),
            },
            {
                "question": "Quantas vezes tenho de voltar?",
                "answer": (
                    "Um episódio isolado costuma resolver-se numa consulta, "
                    "com uma reavaliação a seguir. Se for colocada uma "
                    "órtese, o acompanhamento faz-se ao longo de algumas "
                    "semanas, com ajustes."
                ),
            },
        ],
    },
    {
        "slug": "micose-na-unha-do-pe",
        "name": "Micose na unha do pé",
        "display_order": 20,
        "meta_title": "Micose na unha do pé (onicomicose): tratamento em Coimbra",
        "meta_description": (
            "Unha amarelada, grossa ou a esfarelar pode ser micose. Saiba "
            "como se distingue, porque não passa sozinha e como é tratada em "
            "Coimbra."
        ),
        "keywords": (
            "micose na unha do pé, onicomicose, fungo na unha, unha amarela, "
            "unha grossa, micose unha tratamento Coimbra"
        ),
        "summary": (
            "A unha muda de cor, engrossa e começa a esfarelar-se. Não é "
            "sujidade e não sai a esfregar: é um fungo instalado dentro da "
            "unha, e não desaparece sem tratamento."
        ),
        "what_it_is": (
            "A onicomicose é uma infeção da unha por fungos. Costuma começar "
            "num canto, como uma mancha branca ou amarelada, e vai avançando "
            "para a base. Com o tempo a unha engrossa, perde brilho, "
            "esfarela-se nas pontas e pode descolar-se do leito. É comum e "
            "não tem nada de vergonhoso — mas também não se resolve "
            "sozinha."
        ),
        "why_it_happens": (
            "Os fungos gostam de calor, humidade e escuridão, e um sapato "
            "fechado é as três coisas. Piscinas, balneários e chuveiros "
            "partilhados são sítios de contágio frequente. O risco sobe com "
            "a idade, com a diabetes, com problemas de circulação e com "
            "unhas já traumatizadas — uma unha que levou uma pancada é uma "
            "porta aberta."
        ),
        "warning_signs": (
            "Mudança de cor — amarelo, castanho, esbranquiçado. Unha mais "
            "grossa ou quebradiça. Pó ou farelo por baixo da unha. Mau "
            "cheiro. Dor ao calçar por a unha ter engrossado. Se tem "
            "diabetes, não espere: qualquer alteração numa unha merece ser "
            "vista."
        ),
        "how_we_treat": (
            "Primeiro confirma-se o que se está a ver: nem toda a unha "
            "amarela é micose, e tratar como fungo o que não é fungo perde "
            "meses. Havendo indicação, faz-se o desbaste da unha para "
            "reduzir a espessura e a carga de fungo, e articula-se o "
            "cuidado com o tratamento antifúngico adequado ao caso. Quando "
            "há sinais que exigem diagnóstico médico ou medicação oral, o "
            "encaminhamento faz parte do trabalho — dizer-lhe que precisa de "
            "um médico é também tratar de si."
        ),
        "home_care": (
            "Seque bem os pés, sobretudo entre os dedos. Use chinelos em "
            "balneários e piscinas. Alterne os sapatos para que sequem entre "
            "utilizações e prefira meias que respirem. Não partilhe corta-"
            "unhas nem limas. E tenha paciência: uma unha do pé leva meses a "
            "crescer, e a melhoria vê-se pela parte nova que nasce, não pela "
            "parte velha."
        ),
        "questions": [
            {
                "question": "Quanto tempo demora a curar uma micose na unha?",
                "answer": (
                    "A unha do pé cresce devagar — a renovação completa leva "
                    "vários meses, por vezes perto de um ano no dedo grande. "
                    "O sinal de que está a resultar é a unha nova a nascer "
                    "limpa junto à base, e não a parte já danificada a "
                    "recuperar aspeto."
                ),
            },
            {
                "question": "A micose na unha é contagiosa?",
                "answer": (
                    "Pode passar para as outras unhas, para a pele do pé e "
                    "para outras pessoas em ambientes húmidos partilhados. "
                    "Não partilhar corta-unhas e usar chinelos em balneários "
                    "reduz muito esse risco."
                ),
            },
            {
                "question": "Posso pintar as unhas se tiver micose?",
                "answer": (
                    "O verniz esconde o problema, dificulta a observação da "
                    "evolução e mantém a unha tapada. Durante o tratamento é "
                    "preferível evitar — e é uma conversa a ter na consulta, "
                    "porque depende do caso."
                ),
            },
        ],
    },
    {
        "slug": "calos-e-calosidades",
        "name": "Calos e calosidades",
        "display_order": 30,
        "meta_title": "Calos e calosidades nos pés: tratamento em Coimbra",
        "meta_description": (
            "Um calo não é um problema de pele: é a marca de uma pressão. "
            "Veja porque se formam, como são removidos sem dor e como evitar "
            "que voltem."
        ),
        "keywords": (
            "calos nos pés, calosidades, remoção de calos Coimbra, calo "
            "plantar, pele dura no pé, olho de galo"
        ),
        "summary": (
            "A pele engrossa onde é pressionada, e é isso que um calo é: uma "
            "defesa. Removê-lo alivia logo — mas se a pressão continuar, ele "
            "volta. Tratar bem é tratar as duas coisas."
        ),
        "what_it_is": (
            "Calosidade é pele espessada em resposta a atrito ou pressão "
            "repetidos, geralmente na planta do pé ou nos dedos. O calo "
            "propriamente dito é mais localizado e tem um núcleo que aponta "
            "para dentro — é esse núcleo que faz a dor parecer a de uma "
            "pedra dentro do sapato."
        ),
        "why_it_happens": (
            "Quase sempre por uma de três razões, muitas vezes as três ao "
            "mesmo tempo: calçado que aperta ou que faz o pé escorregar, a "
            "forma como o peso se distribui ao caminhar, e alterações da "
            "estrutura do pé como joanetes ou dedos em garra. A pele não "
            "está a falhar — está a proteger o que está por baixo."
        ),
        "warning_signs": (
            "Dor ao caminhar ou ao estar de pé. Pele amarelada e dura, ou um "
            "ponto muito localizado que dói ao pressionar. Fissuras no meio "
            "da calosidade. Vermelhidão à volta, calor ou líquido — sinais "
            "de que a pele cedeu por baixo e que exigem observação rápida, "
            "sobretudo em pessoas com diabetes."
        ),
        "how_we_treat": (
            "O excesso de pele é removido com material próprio e "
            "esterilizado, sem queimar e sem produtos agressivos. Retirado o "
            "núcleo do calo, o alívio costuma ser imediato. Depois vem a "
            "parte que faz a diferença a longo prazo: perceber de onde vem a "
            "pressão. Muitas vezes a conversa sobre o calçado vale mais do "
            "que o procedimento."
        ),
        "home_care": (
            "Hidrate a planta dos pés todos os dias — pele hidratada racha "
            "menos. Prefira sapatos com espaço à frente e sola que amorteça. "
            "Evite calicidas de farmácia sem indicação: são ácidos, não "
            "distinguem pele doente de pele sã, e em pés com diabetes ou má "
            "circulação podem causar feridas."
        ),
        "questions": [
            {
                "question": "A remoção de calos dói?",
                "answer": (
                    "Não deve doer. Está a ser removida pele já morta e "
                    "espessada; a sensação habitual é de alívio da pressão. "
                    "Se doer, diga — quer dizer que se chegou a pele viva e "
                    "o procedimento ajusta-se."
                ),
            },
            {
                "question": "Porque é que o calo volta sempre?",
                "answer": (
                    "Porque a pressão que o formou continua lá. Enquanto o "
                    "calçado, a pisada ou a forma do pé mantiverem o atrito "
                    "no mesmo sítio, a pele volta a defender-se. É por isso "
                    "que a consulta não acaba na remoção."
                ),
            },
            {
                "question": "Posso usar calicidas ou lixas em casa?",
                "answer": (
                    "Uma lima suave em pele seca, com moderação, costuma ser "
                    "segura. Calicidas com ácido são outra conversa e não se "
                    "recomendam sem indicação, sobretudo a quem tem diabetes "
                    "ou problemas de circulação."
                ),
            },
        ],
    },
    {
        "slug": "pe-diabetico",
        "name": "Risco Podológico",
        "display_order": 40,
        "meta_title": "Pé diabético: cuidados e vigilância em Coimbra",
        "meta_description": (
            "Na diabetes, um pequeno problema no pé deixa de ser pequeno. "
            "Saiba o que vigiar, com que frequência, e em que consiste a "
            "consulta de risco podológico em Coimbra."
        ),
        "keywords": (
            "pé diabético, cuidados com os pés diabetes, pé diabético "
            "Coimbra, ferida no pé diabético, risco podológico, neuropatia "
            "diabética pés"
        ),
        "summary": (
            "A diabetes muda duas coisas nos pés: a sensibilidade e a "
            "circulação. Juntas, fazem com que uma pequena ferida possa "
            "passar despercebida e demorar a sarar. A vigilância regular é o "
            "que evita que se torne grave."
        ),
        "what_it_is": (
            "Risco podológico é o nome que se dá à probabilidade de um pé "
            "vir a ter uma complicação — uma ferida que não fecha, uma "
            "infeção, uma lesão que passou despercebida. A diabetes é a causa "
            "mais frequente, por afetar ao mesmo tempo a sensibilidade e a "
            "circulação, mas não é a única. Não é uma doença que se apanha de "
            "um dia para o outro: é um risco que se avalia e se acompanha."
        ),
        "why_it_happens": (
            "Níveis de glicose elevados durante anos afetam os nervos e os "
            "vasos mais pequenos, que são precisamente os que chegam aos "
            "pés. Com os nervos afetados, uma bolha ou uma pedra dentro do "
            "sapato podem não ser sentidas. Com a circulação afetada, o que "
            "seria uma ferida banal demora mais a fechar."
        ),
        "warning_signs": (
            "Qualquer ferida, bolha, fissura ou mancha que não estava lá. "
            "Formigueiro, dormência ou ardor. Pele muito seca ou a gretar. "
            "Alteração de cor ou de temperatura do pé. Unha encravada ou "
            "calosidade dolorosa. Na diabetes, nenhuma destas coisas deve "
            "esperar para ver se passa — devem ser observadas."
        ),
        "how_we_treat": (
            "A consulta começa por uma avaliação do risco: sensibilidade, "
            "estado da pele e das unhas, pontos de pressão, calçado. A "
            "partir daí definem-se os cuidados e a periodicidade da "
            "vigilância, que não é igual para toda a gente. O corte de unhas "
            "e o tratamento de calosidades são feitos com o cuidado "
            "acrescido que estes pés exigem. Havendo sinais que precisem de "
            "avaliação médica, o encaminhamento é parte do trabalho."
        ),
        "home_care": (
            "Observe os pés todos os dias, incluindo a planta e entre os "
            "dedos — um espelho ajuda. Lave com água morna, nunca quente, e "
            "seque bem entre os dedos. Hidrate a pele, mas não entre os "
            "dedos. Nunca ande descalço. Sacuda o sapato antes de o calçar. "
            "E não trate calos ou unhas com lâminas ou ácidos em casa."
        ),
        "questions": [
            {
                "question": "De quanto em quanto tempo devo vigiar os pés?",
                "answer": (
                    "Em casa, todos os dias. A periodicidade da consulta "
                    "depende do risco avaliado — há pessoas que precisam de "
                    "uma vigilância mais próxima do que outras, e é isso que "
                    "a avaliação define."
                ),
            },
            {
                "question": "Posso cortar as unhas sozinho se tiver diabetes?",
                "answer": (
                    "Depende da sua sensibilidade, da sua visão e da sua "
                    "destreza. Muita gente pode, com cuidados. Quem não "
                    "sente bem os pés ou não os alcança com conforto não "
                    "deve arriscar — o corte passa a ser feito na consulta."
                ),
            },
            {
                "question": "Tenho uma ferida pequena no pé. Posso esperar?",
                "answer": (
                    "Não. Numa pessoa com diabetes, uma ferida pequena é "
                    "motivo para ser vista depressa, mesmo que não doa — "
                    "sobretudo se não doer."
                ),
            },
        ],
    },
    {
        "slug": "verruga-plantar",
        "name": "Verruga plantar",
        "display_order": 50,
        "meta_title": "Verruga plantar (olho de peixe): tratamento em Coimbra",
        "meta_description": (
            "A verruga plantar dói como uma pedra no sapato e confunde-se "
            "com um calo. Veja como se distingue, porque aparece e como é "
            "tratada em Coimbra."
        ),
        "keywords": (
            "verruga plantar, olho de peixe no pé, verruga na planta do pé, "
            "verruga plantar tratamento, HPV pé"
        ),
        "summary": (
            "Dói ao pisar, parece um calo, mas não é: a verruga plantar é "
            "causada por um vírus. Distingui-la do calo muda o tratamento por "
            "completo."
        ),
        "what_it_is": (
            "É uma lesão da pele da planta do pé causada pelo vírus do "
            "papiloma humano. Como fica numa zona que suporta o peso do "
            "corpo, cresce para dentro em vez de para fora, o que a torna "
            "dolorosa e a faz parecer um calo. A diferença clássica: o calo "
            "dói ao pressionar de cima, a verruga dói ao apertar de lado."
        ),
        "why_it_happens": (
            "O vírus entra por pequenas fissuras da pele e apanha-se em "
            "pisos húmidos e partilhados — balneários, piscinas, ginásios. "
            "Andar descalço nesses sítios é o caminho habitual. Nem toda a "
            "gente exposta desenvolve verrugas: a resposta de cada sistema "
            "imunitário conta."
        ),
        "warning_signs": (
            "Dor ao caminhar num ponto específico. Pequenos pontos escuros "
            "dentro da lesão. Interrupção das linhas naturais da pele — num "
            "calo elas continuam por cima, numa verruga são desviadas. "
            "Aparecimento de várias lesões próximas. Se sangra, muda "
            "depressa de aspeto ou não melhora, deve ser observada."
        ),
        "how_we_treat": (
            "O primeiro passo é distinguir a verruga de uma calosidade, "
            "porque o tratamento é diferente e tratar uma como a outra não "
            "resolve nem uma nem outra. Confirmada a verruga, faz-se o "
            "desbaste da pele espessada por cima — que já alivia a dor de "
            "pisar — e define-se o plano de tratamento adequado ao caso e ao "
            "número de lesões. Verrugas plantares são persistentes: o "
            "acompanhamento faz parte."
        ),
        "home_care": (
            "Não ande descalço em balneários, piscinas nem em casa se houver "
            "mais pessoas. Não partilhe toalhas nem calçado. Evite mexer, "
            "cortar ou raspar a lesão — é assim que ela se espalha para "
            "outros pontos do pé. Lave as mãos depois de tocar no pé."
        ),
        "questions": [
            {
                "question": "Como distingo uma verruga plantar de um calo?",
                "answer": (
                    "O calo dói quando se pressiona diretamente; a verruga "
                    "dói sobretudo quando se aperta de lado. E as linhas "
                    "naturais da pele passam por cima de um calo mas "
                    "contornam uma verruga. Na dúvida, deve ser observada — "
                    "o tratamento não é o mesmo."
                ),
            },
            {
                "question": "As verrugas plantares desaparecem sozinhas?",
                "answer": (
                    "Algumas desaparecem com o tempo, quando o sistema "
                    "imunitário responde. Outras persistem durante anos, "
                    "multiplicam-se e doem. Tratar encurta o processo e "
                    "reduz o risco de espalhar."
                ),
            },
            {
                "question": "Vou poder andar normalmente depois?",
                "answer": (
                    "O desbaste da pele espessada costuma aliviar logo a dor "
                    "de pisar. O plano de tratamento define-se na consulta, "
                    "consoante o tamanho, o número e a localização das "
                    "lesões."
                ),
            },
        ],
    },
    {
        "slug": "fissuras-nos-calcanhares",
        "name": "Fissuras nos calcanhares",
        "display_order": 60,
        "meta_title": "Fissuras nos calcanhares (gretas): tratamento em Coimbra",
        "meta_description": (
            "Calcanhares gretados não são só uma questão estética: uma "
            "fissura funda é uma porta de entrada. Veja porque acontecem e "
            "como se tratam em Coimbra."
        ),
        "keywords": (
            "fissuras nos calcanhares, gretas nos pés, calcanhares gretados, "
            "pele seca nos pés, rachadura no calcanhar"
        ),
        "summary": (
            "A pele do calcanhar engrossa, perde elasticidade e acaba por "
            "abrir. Enquanto é superficial incomoda; quando fica funda, "
            "sangra, dói a andar e pode infetar."
        ),
        "what_it_is": (
            "As fissuras são fendas na pele espessada do bordo do calcanhar. "
            "Começam como linhas superficiais e, se a pele continuar seca e "
            "sob pressão, aprofundam-se até atingirem camadas com vasos e "
            "terminações nervosas — é aí que passam a sangrar e a doer."
        ),
        "why_it_happens": (
            "Pele seca é a base, e a pressão faz o resto: estar muito tempo "
            "de pé, excesso de peso, chinelos e sandálias sem apoio atrás, "
            "banhos muito quentes e demorados. Algumas condições de saúde "
            "tornam a pele mais seca, entre elas a diabetes e as alterações "
            "da tiroide."
        ),
        "warning_signs": (
            "Linhas brancas ou amareladas no bordo do calcanhar. Dor ao "
            "andar ou ao estar de pé. Sangue na meia. Vermelhidão, calor ou "
            "líquido à volta da fenda — sinais de infeção, que numa pessoa "
            "com diabetes exigem observação rápida."
        ),
        "how_we_treat": (
            "Remove-se com cuidado o excesso de pele espessada que impede a "
            "fissura de fechar — enquanto ela lá estiver, a fenda reabre "
            "sempre. A seguir trabalha-se a hidratação com o produto "
            "adequado ao seu tipo de pele, que não é o mesmo para toda a "
            "gente, e vê-se o calçado, que muitas vezes é metade do "
            "problema."
        ),
        "home_care": (
            "Hidrate os calcanhares todos os dias, de preferência à noite, "
            "com um creme próprio para pele espessada. Prefira calçado "
            "fechado atrás quando estiver muito tempo de pé. Banhos mornos e "
            "curtos em vez de quentes e longos. E não corte a pele em casa "
            "com lâminas."
        ),
        "questions": [
            {
                "question": "Porque é que o creme sozinho não chega?",
                "answer": (
                    "Porque a camada de pele espessada por cima impede o "
                    "creme de chegar onde é preciso e mantém a fenda aberta "
                    "sob tensão. Removida essa camada, a hidratação passa a "
                    "funcionar."
                ),
            },
            {
                "question": "As fissuras podem infetar?",
                "answer": (
                    "Uma fissura funda é uma porta aberta na pele. Se "
                    "aparecer vermelhidão, calor, inchaço ou líquido, deve "
                    "ser vista — e mais depressa ainda se tiver diabetes."
                ),
            },
        ],
    },
    {
        "slug": "ortese-ungueal",
        "name": "Órtese ungueal",
        "display_order": 70,
        "meta_title": "Órtese ungueal: corrigir a unha sem cirurgia, em Coimbra",
        "meta_description": (
            "A órtese ungueal corrige a curvatura da unha ao longo de "
            "semanas, sem cirurgia. Saiba em que casos se aplica e como "
            "funciona o acompanhamento."
        ),
        "keywords": (
            "órtese ungueal, correção de unha sem cirurgia, unha encravada "
            "recorrente, unha em telha, ortonixia Coimbra"
        ),
        "summary": (
            "Quando a unha encrava sempre no mesmo sítio, o problema não é o "
            "episódio: é a forma da unha. A órtese corrige essa forma "
            "devagar, sem cortar nada."
        ),
        "what_it_is": (
            "É uma pequena peça colocada sobre a unha que exerce uma tensão "
            "suave e contínua, levantando os bordos que estão a penetrar a "
            "pele. Trabalha ao longo de semanas ou meses, acompanhando o "
            "crescimento natural da unha. Não é um penso nem um tratamento "
            "de um dia."
        ),
        "why_it_happens": (
            "Nem todas as unhas encravadas são iguais. Algumas resultam de "
            "um corte mal feito e não voltam a acontecer. Outras vêm de uma "
            "unha excessivamente curva — por herança, por um traumatismo "
            "antigo ou por anos de pressão do calçado — e essas encravam "
            "outra vez, e outra, porque a causa continua lá."
        ),
        "warning_signs": (
            "Unha encravada que volta várias vezes no mesmo dedo. Unha "
            "visivelmente curva, em forma de telha ou de pinça. Dor "
            "recorrente ao calçar. Nestes casos vale a pena avaliar a forma "
            "da unha, e não só tratar o episódio."
        ),
        "how_we_treat": (
            "Avalia-se a curvatura e escolhe-se o tipo de órtese adequado. A "
            "colocação é indolor e feita na consulta. Depois, o "
            "acompanhamento: reavaliações periódicas para ajustar ou "
            "substituir a peça enquanto a unha cresce. A duração depende da "
            "curvatura de partida e do ritmo de crescimento da sua unha — "
            "estima-se na primeira consulta, com honestidade."
        ),
        "home_care": (
            "Mantenha o pé seco e a órtese limpa. Não tente ajustá-la nem "
            "retirá-la. Prefira calçado com espaço à frente durante o "
            "tratamento. Se a peça se soltar ou se sentir dor, marque antes "
            "da data prevista."
        ),
        "questions": [
            {
                "question": "A órtese ungueal dói?",
                "answer": (
                    "A colocação não dói. A tensão é suave e contínua, e o "
                    "habitual é sentir-se alívio da dor que a unha encravada "
                    "causava. Qualquer desconforto persistente deve ser "
                    "comunicado."
                ),
            },
            {
                "question": "Quanto tempo tenho de usar?",
                "answer": (
                    "Depende de quão curva está a unha e da rapidez com que "
                    "ela cresce — as unhas dos pés crescem devagar. Fala-se "
                    "de semanas a meses, e a estimativa é feita na primeira "
                    "consulta."
                ),
            },
            {
                "question": "Posso calçar normalmente?",
                "answer": (
                    "Sim, com bom senso. Calçado que aperte à frente "
                    "contraria o que a órtese está a fazer, por isso é "
                    "preferível evitá-lo durante o tratamento."
                ),
            },
        ],
    },
    {
        "slug": "unhas-grossas-e-deformadas",
        "name": "Unhas grossas e deformadas",
        "display_order": 80,
        "meta_title": "Unhas grossas e deformadas nos pés: tratamento em Coimbra",
        "meta_description": (
            "Unhas que engrossam, escurecem ou mudam de forma têm causas "
            "diferentes — e nem todas são fungo. Veja o que pode estar por "
            "trás e como se trata."
        ),
        "keywords": (
            "unha grossa, unha deformada, onicogrifose, unha escura, unha "
            "com pancada, corte de unhas espessas Coimbra"
        ),
        "summary": (
            "Uma unha que engrossou deixa de se conseguir cortar em casa e "
            "começa a doer dentro do sapato. A causa nem sempre é fungo — e "
            "saber qual é muda o que se faz a seguir."
        ),
        "what_it_is": (
            "É o espessamento e a deformação progressiva da lâmina da unha, "
            "que pode ficar mais dura, curva, escurecida ou irregular. "
            "Quando o espessamento é acentuado e a unha ganha um aspeto "
            "torcido, fala-se de onicogrifose. Seja qual for o nome, o "
            "problema prático é o mesmo: dói e não se corta."
        ),
        "why_it_happens": (
            "As causas são várias e nem sempre a mais óbvia. Um traumatismo "
            "antigo — uma pancada, um sapato apertado durante anos — altera "
            "a matriz onde a unha se forma. Infeções por fungos engrossam a "
            "unha. Psoríase e outras condições de pele também. E a idade, "
            "por si, torna as unhas mais espessas e mais lentas a crescer."
        ),
        "warning_signs": (
            "Unha que não se consegue cortar com um corta-unhas comum. Dor "
            "ao calçar. Escurecimento — que deve sempre ser observado, "
            "porque nem toda a mancha escura é uma pancada. Descolamento da "
            "unha. Alterações rápidas de forma ou de cor."
        ),
        "how_we_treat": (
            "Começa-se por perceber a causa, porque o desbaste alivia mas "
            "não trata o que está por trás. O corte e o desbaste são feitos "
            "com material próprio para unhas espessas, reduzindo a "
            "espessura até o sapato deixar de pressionar. A partir daí "
            "define-se a periodicidade — estas unhas voltam a engrossar, e "
            "o cuidado é regular. Alterações que exijam diagnóstico médico "
            "são encaminhadas."
        ),
        "home_care": (
            "Não force o corte com material que não é para isto: é assim "
            "que as unhas lascam e que a pele em volta é ferida. Amoleça as "
            "unhas com um banho de pés morno antes de tentar cortar. Escolha "
            "calçado que não pressione as unhas de cima. E marque a "
            "reavaliação antes de a unha voltar a incomodar."
        ),
        "questions": [
            {
                "question": "Unha grossa é sempre fungo?",
                "answer": (
                    "Não. Traumatismos antigos, psoríase, alterações de "
                    "circulação e a própria idade engrossam unhas sem "
                    "qualquer fungo envolvido. Tratar como micose o que não "
                    "é micose perde meses."
                ),
            },
            {
                "question": "A unha volta a ficar normal?",
                "answer": (
                    "Depende da causa. Se a matriz da unha foi danificada, a "
                    "unha pode crescer sempre assim — e nesse caso o "
                    "objetivo é mantê-la confortável e sem dor, com "
                    "acompanhamento regular. Isso é dito com clareza na "
                    "consulta."
                ),
            },
            {
                "question": "Tenho uma mancha escura numa unha. É grave?",
                "answer": (
                    "Muitas vezes é sangue de uma pancada que já nem se "
                    "lembra. Mas uma mancha escura que aparece sem "
                    "traumatismo, que cresce ou que se estende à pele à "
                    "volta deve ser observada sem demorar."
                ),
            },
        ],
    },
]
