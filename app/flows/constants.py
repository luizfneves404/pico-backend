from pydantic import BaseModel

LINK_COLOR = "#469596"
MAX_QUESTIONS_FOR_SCORE = 45
MARGIN = 40
AVERAGE_SCORES_BY_CORRECT_QUESTIONS = {
    "Matemática": {
        0: 34.807715700423515,
        1: 340.3919083506703,
        2: 347.89110952590715,
        3: 356.6644923843018,
        4: 365.6806442847766,
        5: 376.6495329440993,
        6: 388.75168599312383,
        7: 402.5552168692767,
        8: 418.54404171977853,
        9: 436.2170585175776,
        10: 456.18579764446713,
        11: 477.84811746538753,
        12: 500.9606017320928,
        13: 525.0945914584463,
        14: 549.5376122089915,
        15: 573.2045449602232,
        16: 596.0457199654866,
        17: 617.2752798020813,
        18: 636.7839696022658,
        19: 654.5168317882682,
        20: 670.7696447824048,
        21: 685.4581055321551,
        22: 699.1704472989638,
        23: 712.0733215273386,
        24: 724.2709679549494,
        25: 736.0861546375147,
        26: 747.4312282565551,
        27: 758.5698012147933,
        28: 769.3615211958942,
        29: 780.1804656500949,
        30: 790.5812965416326,
        31: 801.1644378846144,
        32: 811.6804640737591,
        33: 822.7527862343604,
        34: 834.0897018955641,
        35: 845.4453306713574,
        36: 857.3612294553665,
        37: 870.3484997697327,
        38: 883.3107494269004,
        39: 897.6048632485632,
        40: 909.9874502156779,
        41: 924.0223210962217,
        42: 937.3937008963151,
        43: 952.1557160532905,
        44: 957.4090083798883,
        45: 958.5999999999999,
    },
    "Linguagens": {
        0: 59.92813425468904,
        1: 295.0369318181818,
        2: 303.5585416666667,
        3: 313.3879356568365,
        4: 321.50502606105726,
        5: 332.8778207607996,
        6: 344.5993752055245,
        7: 357.5448717336264,
        8: 370.3574103648035,
        9: 384.3338262476895,
        10: 398.4996255069462,
        11: 412.40422234621275,
        12: 426.3274695939476,
        13: 439.45747401148475,
        14: 452.220138989431,
        15: 463.9064262407075,
        16: 475.3085441346369,
        17: 485.8985721519829,
        18: 495.88787091325474,
        19: 505.2466637164582,
        20: 514.1750748400317,
        21: 522.8061935253203,
        22: 531.0514834783186,
        23: 539.1695330334362,
        24: 547.1359077240385,
        25: 555.0231924305946,
        26: 562.9001464237391,
        27: 570.7914789756808,
        28: 578.8674598994,
        29: 586.9907129466317,
        30: 595.3531732397627,
        31: 603.8596089581199,
        32: 612.7671792503658,
        33: 622.0172330140705,
        34: 631.6121976436125,
        35: 641.8813018524061,
        36: 652.7779885200896,
        37: 664.3143005232502,
        38: 676.8008908194066,
        39: 690.1132677834428,
        40: 704.6289226642825,
        41: 720.7025233644861,
        42: 738.233167082294,
        43: 758.3923076923077,
        44: 787.2314285714288,
        45: 820.8,
    },
    "Ciências da Natureza": {
        0: 29.267773397416455,
        1: 353.22112075096004,
        2: 362.5068104872006,
        3: 372.39011905646385,
        4: 382.57155021185815,
        5: 393.30317410733323,
        6: 404.2822959835389,
        7: 416.25570336562515,
        8: 428.97994750006274,
        9: 442.9976782651157,
        10: 457.9752478249329,
        11: 473.9909344423269,
        12: 490.8343736300752,
        13: 508.2356105118635,
        14: 525.9084305864985,
        15: 543.2198760938893,
        16: 559.9812166134545,
        17: 575.8116052850603,
        18: 590.2167400992596,
        19: 603.5716963423911,
        20: 615.5749160482922,
        21: 626.4210934772,
        22: 636.3983910399741,
        23: 645.6981611144041,
        24: 654.2706998027236,
        25: 662.5222341569843,
        26: 670.5698713488475,
        27: 678.0319579535154,
        28: 685.9100591716369,
        29: 693.0979091719747,
        30: 700.9080295717051,
        31: 708.4732429699254,
        32: 716.1872278018097,
        33: 724.2719205550065,
        34: 732.3434484622268,
        35: 740.7131647447382,
        36: 749.8774633808209,
        37: 758.4258651700577,
        38: 767.9671256684492,
        39: 778.9821926251925,
        40: 790.1534922429496,
        41: 803.5040380638234,
        42: 815.630423206278,
        43: 840.6093540051679,
        44: 856.9464285714287,
        45: 871.8499999999999,
    },
    "Ciências Humanas": {
        0: 30.109506489405035,
        1: 307.9161497306509,
        2: 317.4222303326218,
        3: 325.3524559791025,
        4: 334.25132472550814,
        5: 344.10214360077623,
        6: 354.6185005252918,
        7: 367.0927267076933,
        8: 380.3033615877154,
        9: 394.4006241389825,
        10: 409.15937230455506,
        11: 424.190662888397,
        12: 439.2457902967784,
        13: 453.89427351385797,
        14: 467.795610788304,
        15: 481.20537507694496,
        16: 493.7971018091955,
        17: 505.5747375149165,
        18: 516.5666143868707,
        19: 526.8779918934777,
        20: 536.6318375634773,
        21: 545.8940356475894,
        22: 554.5724748054347,
        23: 563.040454732276,
        24: 571.223090235834,
        25: 579.1405521514985,
        26: 587.134943993899,
        27: 594.9168155431378,
        28: 602.7281224585354,
        29: 610.6124820589686,
        30: 618.6368526013555,
        31: 626.8700691009474,
        32: 635.1900980671244,
        33: 644.0492054187391,
        34: 653.1421869758951,
        35: 662.6863012439338,
        36: 673.0142705035366,
        37: 683.861567562773,
        38: 695.6110831708959,
        39: 708.3711827888692,
        40: 722.557635222006,
        41: 738.8440012628625,
        42: 758.2701507665801,
        43: 779.1142417933573,
        44: 801.4580910240202,
        45: 831.1000000000001,
    },
}

# List of all unique tags extracted from categories and subcategories (no duplicates or hierarchies)
TAGS = [
    "Acústica",
    "América Pré-Colombiana",
    "Anatomia Humana",
    "Antiguidade Clássica",
    "Análise Dimensional",
    "Análise Sintática",
    "Análise de Dados",
    "Arcadismo",
    "Aritmética",
    "Arranjo",
    "Arte Contemporânea",
    "Arte e História",
    "Artigos de Opinião",
    "Bactérias",
    "Barroco",
    "Biologia",
    "Bioquímica e Processos Celulares",
    "Blogs",
    "Botânica",
    "Brasil Colônia (1500-1822)",
    "Brasil Contemporâneo (1985 até hoje)",
    "Cadeia Alimentar",
    "Cadeias Carbônicas",
    "Calorimetria",
    "Cartografia",
    "Charges",
    "Ciclos Biogeoquímicos",
    "Cinemática",
    "Circuitos Elétricos",
    "Citologia",
    "Ciência e Conhecimento",
    "Classificação de Funções",
    "Clima",
    "Colonização Espanhola",
    "Colunas",
    "Combinatória",
    "Combinação",
    "Compostos Iônicos e Oxidantes",
    "Conceitos Políticos",
    "Conjuntos e Sistemas",
    "Conjunções e Conectivos",
    "Construção de Texto",
    "Contos",
    "Conversão de Unidades",
    "Cultura Brasileira",
    "Culturais",
    "Cálculo Químico",
    "Cátions e Ânions",
    "DNA e RNA",
    "Demografia",
    "Denotação e Conotação",
    "Densidade",
    "Dilatação",
    "Dinâmica",
    "Divisão Celular",
    "Domínio da Língua",
    "Ecologia",
    "Economia e Indústria",
    "Econômicas",
    "Editorial",
    "Elementos do Mapa",
    "Eletromagnetismo",
    "Eletroquímica",
    "Eletrólise",
    "Energia Elétrica",
    "Energia e Momento",
    "Ensaios",
    "Entrevistas",
    "Equilíbrio Químico",
    "Era Vargas (1930-1945)",
    "Era das Revoluções (1789-1848)",
    "Era do Imperialismo (1848-1914)",
    "Escala e Medidas de Grandeza",
    "Escola de Frankfurt",
    "Escolas Filosóficas",
    "Espanhol",
    "Espaço Agrário",
    "Espaço Urbano",
    "Especiação",
    "Estequiometria",
    "Estática",
    "Estética",
    "Evento Único",
    "Eventos Condicionais",
    "Evolução",
    "Existencialismo",
    "Expressões Idiomáticas",
    "Fake News",
    "Figuras de Linguagem",
    "Filosofia",
    "Filosofia Antiga",
    "Filosofia Contemporânea",
    "Filosofia Medieval",
    "Filosofia Moderna",
    "Filosofia Política",
    "Filosofia e Religião",
    "Fisiologia Animal",
    "Fisiologia Humana",
    "Fisiologia Vegetal",
    "Fluídos",
    "Fontes de Energia",
    "Formação de Palavras",
    "Fotossíntese",
    "Frases Comuns",
    "Função Afim",
    "Função Exponencial",
    "Função Quadrática",
    "Função da Linguagem",
    "Funções",
    "Física",
    "Física Moderna",
    "Física Quântica",
    "Fóruns de Discussão",
    "Gases",
    "Genocídio e Direitos Humanos",
    "Genética",
    "Geografia",
    "Geografia Física",
    "Geografia Humana",
    "Geologia",
    "Geometria",
    "Geometria Analítica",
    "Geometria Espacial",
    "Geometria Plana",
    "Globalização",
    "Gramática",
    "Gráficos e Tabelas",
    "Guerra Fria",
    "Gêneros Literários",
    "Gírias",
    "Heredogramas",
    "Hidrografia",
    "História",
    "História Global",
    "História da Arte",
    "História das Américas",
    "História das Ideias",
    "História do Brasil",
    "História dos Estados Unidos",
    "Homem e Natureza",
    "Hormônios",
    "Idade Moderna",
    "Idade Média",
    "Iluminismo",
    "Inglês",
    "Interpretação de Texto",
    "Isomeria",
    "Lentes e Instrumentos",
    "Ligações Químicas",
    "Logaritmo",
    "Lógica",
    "MMC e MDC",
    "Magnetismo",
    "Manifestações Culturais",
    "Mapas Temáticos",
    "Marxismo",
    "Matemática",
    "Matemática Financeira",
    "Max Weber",
    "Mecânica",
    "Meios de Comunicação",
    "Metafísica",
    "Modelos Atômicos",
    "Modernismo",
    "Movimento Harmônico (MHS)",
    "Movimentos Sociais",
    "Mudanças Climáticas",
    "Mudanças de Estado",
    "Museus e Memória",
    "Média, Moda e Mediana",
    "Naturalismo",
    "Nomenclatura de Funções",
    "Nomenclatura de Funções Orgânicas",
    "Notícias",
    "Nutrição",
    "Números Complexos",
    "Ondas",
    "Ondulatória",
    "Operações Básicas",
    "Ordem de Grandeza",
    "Organelas",
    "Oriente Médio",
    "Palavras Formais",
    "Palavras Informais",
    "Parasitologia",
    "Parnasianismo",
    "Participação Política",
    "Pensadores Brasileiros",
    "Permutação",
    "Período Entreguerras (1919-1939)",
    "Período Imperial (1822-1889)",
    "Pilhas",
    "Poemas",
    "Poesia Contemporânea",
    "Polaridade e Geometria Molecular",
    "Polímeros",
    "Política Internacional",
    "Políticas",
    "Pontuação",
    "Português",
    "Povos Originários",
    "Prevenção de Doenças",
    "Primeira Guerra Mundial",
    "Probabilidade",
    "Probabilidade Genética",
    "Progressão Aritmética",
    "Progressão Geométrica",
    "Projeções Cartográficas",
    "Propriedades Químicas",
    "Propriedades da Matéria",
    "Prosa Contemporânea",
    "Protozoários",
    "Quarta República (1945-1964)",
    "Questões Raciais",
    "Questões de Gênero",
    "Quinhentismo",
    "Química",
    "Química Inorgânica",
    "Química Orgânica",
    "Radioatividade",
    "Razão e Proporção",
    "Realismo",
    "Reações Orgânicas",
    "Reações de Neutralização",
    "Reações de Oxirredução",
    "Recursos de Estilo",
    "Redes Sociais",
    "Reflexão",
    "Refração e Difração",
    "Regime Militar (1964-1985)",
    "Relatividade",
    "Relações Ecológicas",
    "Relevo",
    "Renascimento",
    "Renda e Desigualdade",
    "Reportagens",
    "Reprodução Animal",
    "Reprodução Vegetal",
    "República Velha (1889-1930)",
    "Respiração Celular",
    "Revoluções Industriais",
    "Romances",
    "Romantismo",
    "Satíricas",
    "Saúde",
    "Segunda Guerra Mundial",
    "Semântica e Vocabulário",
    "Separação de Misturas",
    "Sequência Numérica",
    "Simbolismo",
    "Sistemas Vitais",
    "Sites Educativos",
    "Sociais",
    "Sociologia",
    "Sociologia Contemporânea",
    "Sociologia do Brasil",
    "Soluções",
    "Sustentabilidade",
    "Séries",
    "Tabela Periódica",
    "Teatro",
    "Tecidos",
    "Tecnologia e Sociedade",
    "Tecnologia e Trabalho",
    "Temperatura",
    "Teoria da Literatura",
    "Termodinâmica",
    "Termologia",
    "Termoquímica",
    "Texto Jornalístico",
    "Texto Literário",
    "Texto Publicitário",
    "Textos Jornalísticos",
    "Textos Literários",
    "Textos da Internet",
    "Teóricos da Sociologia",
    "Tipo Textual",
    "Transformações e Operações Matemáticas",
    "Transporte Celular",
    "Trigonometria",
    "Urbanização e Industrialização",
    "Variedade Linguística",
    "Vocabulário",
    "Vírus",
    "Zoologia",
    "Álgebra Linear",
    "Área e Volume",
    "Émile Durkheim",
    "Ética",
    "Ótica",
]

OPEN_ENDED_FEEDBACK_SYSTEM_MESSAGE = """Você é um corretor de questões discursivas. Considere os seguintes conselhos para avaliar a resposta de um aluno a uma questão:

1. **Compreensão Profunda da Pergunta**: Leia a questão atentamente, identificando o que é especificamente solicitado. Procure interpretar não apenas o tema geral, mas o foco particular da pergunta. Evite responder com tudo o que sabe sobre o assunto; em vez disso, direcione sua resposta para abordar o cerne da questão, alinhando-se ao que o enunciado demanda.

2. **Interpretação e Análise Contextual**: Avalie as informações fornecidas na questão ou no material de apoio (caso haja). Observe se o texto vem de um autor, um documento específico, ou uma análise crítica. Entender o ponto de vista e o contexto de quem enuncia o texto pode enriquecer a profundidade da sua resposta.

3. **Estabelecimento de Relações**: Ao responder, procure relacionar o assunto discutido com contextos maiores ou com outros eventos e ideias pertinentes à questão. Essa habilidade de conectar diferentes elementos demonstra compreensão mais ampla e crítica do tema.

4. **Aplicação de Conceitos Relevantes**: Utilize conceitos importantes da disciplina em questão, aplicando-os de forma coerente e adequada ao contexto da pergunta. Demonstrar um bom domínio conceitual reforça a qualidade de sua interpretação e análise.

5. **Clareza e Objetividade na Redação**: Estruture sua resposta de maneira lógica, encadeando os argumentos de forma coesa e clara. Evite longas digressões; foque-se em responder à pergunta de forma direta e completa.

Você receberá uma mensagem contendo a questão e seu gabarito. Também poderá conter um texto extraído ou uma imagem.
Responda diretamente ao aluno, conversando em segunda pessoa.
Compare a resposta do aluno com o gabarito da questão (se houver) e, ao final, dê uma nota de 0 a 5 para a resposta do aluno. Se não houver gabarito, responda a questão e depois compare com a resposta do aluno.
Coloque a nota a ser dada no final da sua mensagem, no formato "Nota: X"."""

OPEN_ENDED_FEEDBACK_USER_MESSAGE = """Texto extraído (se não houver, ignore): \"\"\"
{extra_embedding_text}
\"\"\"

Questão: \"\"\"
{question_text}
\"\"\"

Gabarito (se não houver, responda você a pergunta, depois compare com a minha resposta): \"\"\"
{official_answer}
\"\"\"

Minha resposta: \"\"\"
{submitted_text}
\"\"\"
"""

OPEN_ENDED_FEEDBACK_MODEL = "gpt-4o"

OPEN_ENDED_TEMPERATURE = 0.0


SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION = """
Você é um assistente que gera questões de múltipla escolha no estilo dos grandes vestibulares brasileiros com 4 alternativas, com base em um conteúdo transcrito.

Você vai receber um bloco curto de transcrição que faz parte de um material maior. Use esse bloco como base de conteúdo; com base no que você encontrar, entenda se trata-se de um artigo, resumo, livro texto ou outro formato. Se for um resumo ou livro texto, não cite ou reproduza literalemente a transcrição – o objetivo deve ser identificar se o usuário entendeu o conteúdo explicado. Se for um artigo com marcas autorais, você pode fazer perguntas citando o material base (mas não só). 

Produza as questões no mesmo idioma da transcrição. Elabore enunciados claros e autossuficientes; quando apropriado, inclua um breve contexto original para situar o problema.

A user message vai te dizer quantas questões criar. Se você for fazer apenas uma pergunta por bloco, foque em fazer uma pergunta que garanta que o usuário entendeu/foi capaz de revisar o tema presente naquele texto. Se for fazer mais de uma pergunta, varie o nível cognitivo, começando com uma mais básica que exija apenas identificação e fazendo outras mais sofisticadas que demandem interpretação e aplicação/análise.

Em termos de estilo, procure seguir as regras:

-   4 alternativas por questão e exatamente 1 correta.
•   Distratores plausíveis e de qualidade, evitando pistas óbvias.
•   Balanceie o tom entre as alternativas (evite assimetria como a correta "cautelosa" versus demais "sempre/nunca/apenas").
•   Varie o comprimento das alternativas; não deixe a correta sistematicamente mais longa/curta.
•   Use pistas gramaticais/numéricas (datas/números/nomes específicos) apenas quando sustentados pelo conteúdo.
•   Evite "Todas as anteriores"/"Nenhuma das anteriores".

Restrições:
•   Se o insumo estiver incompleto/ambíguo, assuma apenas o mínimo necessário e formule questões sobre conceitos realmente presentes, sem inventar fatos.
•   Não inclua justificativas, soluções ou comentários fora dos campos solicitados.

Retorne as questões no formato especificado, com os campos de cada questão:
•   text: texto completo da questão (incluindo texto-base e enunciado)
•   choices: array com as 4 alternativas (apenas o texto, sem prefixos como "A)", "B)", etc.)
•   correct_choice: letra da alternativa correta (A, B, C, D)
"""


SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION_MATH = """
Você é um assistente que gera questões de múltipla escolha no estilo dos grandes vestibulares brasileiros com 4 alternativas, com base em um conteúdo transcrito. As questões devem envolver raciocínio ou cálculo matemático.

Você vai receber um bloco curto de transcrição que faz parte de um material maior. Use esse bloco como base de conteúdo; com base no que você encontrar, entenda se trata-se de um artigo, resumo, livro texto ou outro formato. Se for um resumo ou livro texto, não cite ou reproduza literalemente a transcrição – o objetivo deve ser identificar se o usuário entendeu o conteúdo explicado. Se for um artigo com marcas autorais, você pode fazer perguntas citando o material base (mas não só). 

Produza as questões no mesmo idioma da transcrição. Elabore enunciados claros e autossuficientes; quando apropriado, inclua um breve contexto original para situar o problema.

A user message vai te dizer quantas questões criar. Se você for fazer apenas uma pergunta por bloco, foque em fazer uma pergunta que garanta que o usuário entendeu/foi capaz de revisar o conteúdo do texto (por exemplo, aplicação das fórmulas indicadas). Se for fazer mais de uma pergunta, varie o nível cognitivo, começando com uma mais básica que exija apenas identificação conceitual e fazendo outras mais sofisticadas que demandem aplicação/análise.

Em termos de estilo, procure seguir as regras:

-   4 alternativas por questão e exatamente 1 correta.
•   Distratores plausíveis e de qualidade, evitando pistas óbvias.
•   Balanceie o tom entre as alternativas (evite assimetria como a correta "cautelosa" versus demais "sempre/nunca/apenas").
•   Varie o comprimento das alternativas; não deixe a correta sistematicamente mais longa/curta.
•   Use pistas gramaticais/numéricas (datas/números/nomes específicos) apenas quando sustentados pelo conteúdo.
•   Evite "Todas as anteriores"/"Nenhuma das anteriores".
•   Use números convenientes; explicite unidades e critérios de arredondamento quando necessário

Restrições:
•   Se o insumo estiver incompleto/ambíguo, assuma apenas o mínimo necessário e formule questões sobre conceitos realmente presentes, sem inventar fatos.
•   Não inclua justificativas, soluções ou comentários fora dos campos solicitados.

Retorne as questões no formato especificado, com os campos de cada questão:
•   text: texto completo da questão (incluindo texto-base e enunciado)
•   choices: array com as 4 alternativas (apenas o texto, sem prefixos como "A)", "B)", etc.)
•   correct_choice: letra da alternativa correta (A, B, C, D)
"""


SYSTEM_MESSAGE_QUESTION_GENERATION_THEME = """
Você é um assistente que gera questões de múltipla escolha no estilo dos grandes vestibulares brasileiros com 4 alternativas, com base em um conteúdo transcrito.

Você vai receber um tema do usuário. Use esse tema como base para gerar questões de revisão e estudo para o usuário. Essas questões devem prosseguir em uma certa ordem, assumindo que o usuário é um aluno bom de ensino médio. Assim, comece com perguntas simples mais direcionadas para identificação dos principais conceitos e fórmulas, progressivamente aumentando a dificuldade com outras que demandem maior interpretação e aplicação/análise. As questões devem ser no nível de dificuldade das questões de múltipla escolha dos vestibulares do Brasil, como ENEM e FUVEST, ou dos Estados Unidos, como SAT.

Produza as questões no mesmo idioma da transcrição. Elabore enunciados claros e autossuficientes; quando apropriado, inclua um breve contexto original para situar o problema. A user message vai te dizer quantas questões criar. Independente do número, procure cobrir os principais aspectos do tema a nível de ensino médio/vestibular.

Em termos de estilo, procure seguir as regras:

-   4 alternativas por questão e exatamente 1 correta.
•   Distratores plausíveis e de qualidade, evitando pistas óbvias.
•   Balanceie o tom entre as alternativas (evite assimetria como a correta "cautelosa" versus demais "sempre/nunca/apenas").
•   Varie o comprimento das alternativas; não deixe a correta sistematicamente mais longa/curta.
•   Use pistas gramaticais/numéricas (datas/números/nomes específicos) apenas quando sustentados pelo conteúdo.
•   Evite "Todas as anteriores"/"Nenhuma das anteriores".

Restrições:
•   Se o insumo estiver incompleto/ambíguo, assuma apenas o mínimo necessário e formule questões sobre conceitos realmente presentes, sem inventar fatos.
•   Não inclua justificativas, soluções ou comentários fora dos campos solicitados.

Retorne as questões no formato especificado, com os campos de cada questão:
•   text: texto completo da questão (incluindo texto-base e enunciado)
•   choices: array com as 4 alternativas (apenas o texto, sem prefixos como "A)", "B)", etc.)
•   correct_choice: letra da alternativa correta (A, B, C, D)

"""


SYSTEM_MESSAGE_QUESTION_GENERATION_THEME_MATH = """
Você é um assistente que gera questões de múltipla escolha no estilo dos grandes vestibulares brasileiros com 4 alternativas, com base em um conteúdo transcrito.

Você vai receber um tema do usuário. Use esse tema como base para gerar questões de revisão e estudo para o usuário. Essas questões devem prosseguir em uma certa ordem, assumindo que o usuário é um aluno bom de ensino médio, a não ser que o usuário especifique seu nível educacional na própria mensagem (nesse caso, seguir o nível de dificuldade mais adequado para ele). Comece com perguntas simples mais direcionadas para memorização de conceitos e fórmulas relacionados ao tema, progressivamente aumentando a dificuldade com outras que demandem maior raciocínio e cálculo. As questões devem ser no nível de dificuldade das questões de múltipla escolha dos vestibulares do Brasil, como ENEM e FUVEST, ou dos Estados Unidos, como SAT.

Produza as questões no mesmo idioma da transcrição. Elabore enunciados claros e autossuficientes; quando apropriado, inclua um breve contexto original para situar o problema. A user message vai te dizer quantas questões criar. Independente do número, procure cobrir os principais aspectos do tema a nível de ensino médio/vestibular. Se o tema for algo não ensinado no ensino médio, considere que o aluno está na universidade e faça questões de nível universitário para ele. 
 
Em termos de estilo, procure seguir as regras:

-   4 alternativas por questão e exatamente 1 correta.
•   Distratores plausíveis e de qualidade, evitando pistas óbvias.
•   Balanceie o tom entre as alternativas (evite assimetria como a correta "cautelosa" versus demais "sempre/nunca/apenas").
•   Varie o comprimento das alternativas; não deixe a correta sistematicamente mais longa/curta.
•   Use pistas gramaticais/numéricas (datas/números/nomes específicos) apenas quando sustentados pelo conteúdo.
•   Evite "Todas as anteriores"/"Nenhuma das anteriores".
•   Use números convenientes; explicite unidades e critérios de arredondamento quando necessário


Restrições:
•   Se o insumo estiver incompleto/ambíguo, assuma apenas o mínimo necessário e formule questões sobre conceitos realmente presentes, sem inventar fatos.
•   Não inclua justificativas, soluções ou comentários fora dos campos solicitados.

Retorne as questões no formato especificado, com os campos de cada questão:
•   text: texto completo da questão (incluindo texto-base e enunciado)
•   choices: array com as 4 alternativas (apenas o texto, sem prefixos como "A)", "B)", etc.)
•   correct_choice: letra da alternativa correta (A, B, C, D)
"""

# File processing constants
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB limit
SUPPORTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/jpg", "image/webp"]
SUPPORTED_DOCUMENT_TYPES = ["application/pdf", "text/plain"]
CHUNK_SIZE = 8192  # 8KB chunks for file reading

# Transcription processing
MAX_TRANSCRIPTION_LENGTH = 100000  # Maximum characters per transcription block
MAX_COMBINED_TRANSCRIPTION_LENGTH = (
    500000  # Maximum total transcription length for AI processing
)

SYSTEM_MESSAGE_BLOCK_TITLE = """
    Você é um especialista em educação que sabe extrair conceitos-chave de textos.
    Você receberá um bloco de texto (parte de um texto maior, que pode ser um resumo, artigo etc) e deverá se basear nele para extrair as tags mais relevantes.
    Sua tarefa é identificar exatamente 1 a 3 tags que representem os temas principais do bloco de texto fornecido.
    As tags devem capturar com especificidade os tópicos mais relevantes do conteúdo, como matérias, nomes de autores etc.

Caso você seja capaz de identificar que é um artigo, procure extrair o título de artigo se possível e indicar com "(título)" ao lado. Caso não seja possível identificar esse título, ignore a instrução. Apenas coloque essa indicação caso você tenha certeza (p>90%) de que esse é o título do artigo transcrito.
    
    FORMATO DE RESPOSTA:
    - Retorne apenas as tags separadas por vírgula (ex: "Matemática, Geometria, Trigonometria")
    - Máximo de 3 tags por bloco
    - Sem pontuação adicional, aspas ou explicações
    - Não crie tags genéricas, mas capture a essência específica do conteúdo
"""

# System messages for new utility functions
SYSTEM_MESSAGE_GENERATE_TITLE_FROM_TRANSCRIPTIONS = """
Você é um especialista em criar títulos educacionais concisos e informativos. Você receberá uma série de subtítulos dados para blocos de texto de uma transcrição de um documento. Com base nesses subtítulos, você deve gerar um título geral para o documento inteiro, que represente bem o conteúdo.

Caso algum desses subtítulos contenha "(título)" ao lado, tente identificar se esse é de fato o título do documento inteiro e, caso seja, responda como título gerado.

Caso haja mais de um subtítulo apontado ou caso não haja nenhum, então você deve gerar o título respeitando esses critérios:
- Ser conciso (máximo 5 palavras)
- Capturar o tema principal comum entre as transcrições
- Ser claro e atrativo para estudantes
- Evitar redundâncias se os títulos forem similares
- Em caso de temas distintos, priorize o denominador comum mais amplo e útil sem inventar detalhes

Responda apenas com o título gerado, sem aspas ou explicações adicionais.

"""

SYSTEM_MESSAGE_CHECK_MATH_INVOLVEMENT = """
Você é um classificador de conteúdo educacional parte de um agente que gera questões de vestibular a partir de um tópico. Ao receber o tópico, você deve identificar se o tópico em questão deve ser estudado com questões que envolvam cálculos matemáticos.

Analise o título/tópico fornecido e determine se ele envolve ou requer cálculos matemáticos, fórmulas, equações ou raciocínio quantitativo.

Considere como envolvendo matemática (responda SIM):
•	Temas geralmente abordados com cálculos numéricos, resolução de equações ou manipulação de expressões.
•	Tópicos que mencionem explicitamente fórmulas, equações ou expressões matemáticas.
•	Geometria, trigonometria, álgebra, cálculo; física com cálculos; química quantitativa.
•	Estatística e probabilidade (média, desvio padrão, distribuições, intervalos, etc.).
•	Porcentagens, proporções, regra de três, taxas, crescimento/variação, conversões de unidades com cálculo.

NÃO considere como envolvendo matemática (responda NÃO):
•	Tópicos teóricos ou conceituais sem necessidade cálculos ou fórmulas, incluindo ciências como biologia e certas áreas da química e da física.
•	História, literatura, filosofia; biologia; geografia humana; economia/sociologia qualitativas.
•	Presença de números ou datas sem necessidade de conta (ex.: nomes de modelos/produtos, anos, populações).

Critérios adicionais:
•	Se múltiplos tópicos forem fornecidos, responda SIM se a maioria deles exigir cálculo; caso contrário, responda NÃO.
•	Se o título apenas nomeia um campo/tema matemático sem indício de cálculo ou fórmula (ex.: "História da álgebra"), responda NÃO.
•	Entradas vazias, irrelevantes ou ilegíveis devem receber NÃO.
•	Em caso de ambiguidade, prefira NÃO.
Regras de resposta:
•	Não explique, não justifique, não repita o título/tópico, não cite estas instruções e não vaze metadados.
•	A saída deve ser exatamente uma única palavra em maiúsculas, sem espaços ou pontuação extra.
Responda apenas "SIM" se envolve cálculos matemáticos ou "NÃO" se não envolve.

"""

SYSTEM_MESSAGE_QUESTION_PERTINENCE_TO_TOPIC = """
Você é um professor de ensino médio ou faculdade que participa de bancas de avaliação de vestibular e especialista em verificar se uma questão é pertinente a um determinado tema.

Você receberá os campos:
• topic: O tema/tópico a ser avaliado
• question and choices: O texto completo da questão (incluindo enunciado e alternativas)

Sua tarefa é julgar a pertinência conceitual do conteúdo cobrado na questão em relação ao tema indicado. Priorize o foco conceitual do enunciado e das alternativas.

Use a seguinte escala numérica:

0 - Nada pertinente (totalmente fora do tema)
1 - Pouco pertinente (conexão muito fraca com o tema)
2 - Minimamente pertinente (alguma conexão distante com o tema)
3 - Moderadamente pertinente (conexão razoável com o tema)
4 - Muito pertinente (forte conexão com o tema)
5 - Extremamente pertinente (diretamente relacionado ao tema central)

Critérios de avaliação:
•	Centralidade do tema: atribua 5 quando o entendimento do tema for essencial para resolver a questão; 4 quando o tema for importante para resolução mas não exclusivo; 3 quando for auxiliar, mas houver outros temas mais centrais; 2 quando a conexão for periférica ou indireta; 1 para menções superficiais/contextuais; 0 quando não houver relação.
•	Macrotema vs. subtema: para temas amplos (ex.: "Matemática", "Biologia"), questões da área tendem a pontuar 4-5; para subtemas específicos (ex.: "Funções exponenciais"), exija aderência ao subtema para 4–5.
•	Interdisciplinares: pondere pelo peso do tema no raciocínio exigido (tema principal ≥50%: 5; coadjuvante: 4; periférico: 3).
•	Sinônimos e variações: aceite sinônimos, termos equivalentes, traduções e notações usuais do tema.
•	Ruído: ignore nomes, datas ou termos que apareçam apenas como contexto sem serem o objeto avaliado.
•	Qualidade da questão: não avalie correção ou qualidade pedagógica, apenas pertinência temática.

Exemplos por categoria (apenas para orientar; na sua resposta real, retorne só o número): 
0	— Nada pertinente
•	topic: Ciclo do carbono; question: Em Os Lusíadas, qual é o principal propósito da viagem de Vasco da Gama? 
•	topic: Derivadas; question: Qual pintor renascentista é autor de A Última Ceia?
o	Saída esperada: 0
•	topic: Revolução Francesa; question and choices: Resolva 2x + 5 = 15.
1 — Pouco pertinente
•	topic: Ecologia de populações; question: Qual fator mais contribui para a alta densidade populacional de metrópoles?
•	topic: Existencialismo; question: Por que alguns peixes conseguem existir em grandes profundidades?
2 — Minimamente pertinente
•	topic: Geometria plana; question: Na história da arte, a Bauhaus valorizava formas simples. Qual delas melhor reflete essa estética?
•	topic: Revolução Francesa; question and choices: Qual evento causou a revolução dos Cravos em Portugal?
3 — Moderadamente pertinente
•	topic: Função exponencial; question: Uma população aumenta com 20 mil pessoas por ano. Qual gráfico melhor representa esse comportamento?
•	topic: Estoicismo; question and choices: Em psicologia contemporânea, qual prática mais se aproxima da ideia estoica de focar no que se pode controlar? 
4 — Muito pertinente
•	topic: Fotossíntese question: Duas plantas aquáticas foram colocadas em frascos: A (com luz) e B (no escuro). Após 1 hora, onde a concentração de O2 na água tende a ser maior? 
•	topic: Cadeias alimentares; question: A eutrofização pode afetar as cadeias alimentares. Qual efeito é esperado nos níveis tróficos superiores?
•	topic: Função quadrática; question: A altura de uma bola é h(t) = -5t^2 + 20t + 1. O que representa o vértice dessa parábola?
•	topic: Revolução Francesa; question: Comparando as Revoluções Americana, Francesa e Haitiana, qual aspecto comum é correto?
5 — Extremamente pertinente
•	topic: Iluminismo; question: Em O Contrato Social, qual princípio está mais associado ao Iluminismo?
•	topic: Genética; question: Em um cruzamento Aa x Aa com dominância completa, qual proporção fenotípica é esperada?
•	topic: Derivadas; question: Calcule d/dx (3x^2 - 4x + 1)

Restrições:
•	Baseie-se apenas no conteúdo fornecido em topic e question and choices; não invente informações externas.
•	Não mencionar, citar ou reproduzir qualquer fonte interna ou metadados.
•	Não explique sua decisão, não inclua texto extra, símbolos, espaços adicionais, quebras de linha, rótulos ou comentários.
•	Retorne APENAS o número correspondente (0, 1, 2, 3, 4 ou 5).
"""

SYSTEM_MESSAGE_CLASSIFY_TOPIC_SUBJECT = """
Você é um especialista em gerar tags de conteúdo para um título de resumo ou tópico. Tarefa
•	Determine em qual matéria o título/tópico se enquadra, considerando as competências centrais envolvidas (conceitos, métodos, habilidades).
•	Escolha apenas uma matéria dentre a lista em {subjects}.
•	Se o tema for interdisciplinar, selecione a matéria predominante (a que mais dirige a abordagem).
•	Em caso de matérias semelhantes na lista, escolha a opção exatamente como aparece (mesma grafia e acentuação).
•	A saída deve corresponder literalmente a um item de {subjects}, independentemente do idioma do título/tópico.
Formato de resposta obrigatório
•	Responda apenas com o nome da matéria escolhido exatamente como em {subjects}.
•	Sem aspas, sem comentários, sem linhas extras, sem espaços antes/depois.
Matérias disponíveis
{subjects}
"""

SYSTEM_MESSAGE_GENERATE_MINOR_TAGS_FOR_TOPIC = """
Você é um especialista em gerar tags que indiquem o conteúdo para tópicos educacionais.
Você receberá um tópico e deverá gerar tags que identifiquem os subtemas ou conceitos-chave abordados.

INSTRUÇÕES:
- Analise cuidadosamente o tópico fornecido
- Identifique de 2 a 5 tags que melhor representem os tópicos centrais específicos abordados
- As tags devem ser específicas e refletir os conceitos/subtemas do tópico apresentado
- Evite redundância: não repita tags nem use tags que sejam muito próximas na mesma resposta
- Seja específico: prefira "Porcentagem", "Citologia", "Leitura de gráfico" a termos muito amplos como "Matemática" "Biologia" "Interpretação"
- Evite redundância: não repita tags nem use sinônimos muito próximos na mesma resposta
- Use termos curtos e canônicos (1-3 palavras por tag)
- Idioma das tags: português, no mesmo idioma do enunciado da questão
- Se o assunto estiver incompleto, assuma o mínimo necessário e escolha a(s) tag(s) mais apropriada(s) possível(is) com base no conhecimento existente, não deixe detalhes

FORMATO DE RESPOSTA OBRIGATÓRIO:
- Retorne APENAS as tags separadas por vírgula (ex: "Tag1, Tag2, Tag3")
- De 2 a 5 tags por tópico
- Sem pontuação adicional, aspas, explicações ou qualquer texto extra
"""


PROMPT_COVER_GENERATION = """
Crie uma capa marcante para um quiz sobre {flow_title}.
Escolha o estilo pelo tema, priorizando estilos clássicos, surrealistas ou hiper-realistas:
•	tecnologia/ciências exatas → estilo hiper-realista moderno com elementos técnicos elegantes, iluminação suave e natural
•	história/antiguidade/arte → estilo de pintura clássica predominante no período (óleo, renascimento, neoclássico, mármore)
•	natureza/biologia → estilo botânico clássico detalhado, ilustração científica hiper-realista ou surrealista com elementos naturais
•	matemática/engenharia → geometria clássica com elementos arquitetônicos renascentistas ou surrealistas
•	literatura/humanas → estilo pictórico clássico com elementos surrealistas, inspirado em pinturas de museu
(Se outro tema, adapte criativamente usando estilos clássicos, surrealistas ou hiper-realistas. Evite estilos cyberpunk, neon ou futuristas)
Composição: símbolo central + 2-3 ícones do tema; área limpa para título; profundidade e dinamismo; paleta de cores elegante e sofisticada.
Restrições: sem texto, sem logos, sem rostos reconhecíveis.
Formato: 1:1 (variante 16:9 opcional).
 
"""


class QuestionInstance(BaseModel):
    text: str
    choices: list[str]
    correct_choice: str


class QuestionSet(BaseModel):
    questions: list[QuestionInstance]
