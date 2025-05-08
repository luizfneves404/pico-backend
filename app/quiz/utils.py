import asyncio
import base64
import json
import logging
import re
from typing import Any

from openai import BadRequestError, RateLimitError

import app.shared.openai_utils as openai_utils
from app.quiz.models import ENEM_AREAS, Question, SessionQuestion

# API_KEY = settings.MARITACA_API_KEY
# client = OpenAI(
#     api_key=API_KEY, base_url="https://chat.maritaca.ai/api", timeout=10, max_retries=5
# )


# def call_sabia_chat_completions_create(
#     model: str,
#     temperature: float,
#     messages: list[ChatCompletionMessageParam],
#     json_mode: bool,
#     timeout: int,
# ) -> ChatCompletion:
#     sanitized_messages = sanitize_messages(messages)
#     logger.debug(
#         f"External API call to OpenAI: Creating chat completion with model '{model}', temperature '{temperature}' and json_mode '{json_mode}' for messages '{sanitized_messages}'"
#     )
#     response = client.with_options(timeout=timeout).chat.completions.create(
#         model=model,
#         temperature=temperature,
#         messages=messages,
#     )
#     logger.debug(
#         f"From OpenAI, received a chat completion response: '{response.choices[0].message.content}'"
#     )
#     return response

S3_BUCKER_PREFIX = "https://pico-backend-django-private.s3.sa-east-1.amazonaws.com/"

SYSTEM_MESSAGE_VALIDATION = """Você é um professor especializado em vestibulares.
A seguir, você receberá uma questão de vestibular com a categoria e a subcategoria já determinadas.

Sua tarefa é verificar se a categorização está correta, analisando a qualidade da categorização antes de responder. Responda "Sim" se a qualidade da categorização for superior a um limiar de 8/10 (80%), caso contrário, responda "Não".

Não escreva NENHUMA outra explicação ou detalhamento além de "Sim" ou "Não".

Questão: {question_extra_embedding_text} ; {question_text}
Categoria: {category}
Subcategoria: {subcategory}
Alternativas:
{choices}
"""


SYSTEM_MESSAGE_CATEGORY = """Você é um professor especializado em vestibulares e deve categorizar as questões de vestibular que são enviadas a você.

Abaixo você possui uma lista de categorias, bem como as subcategorias, apenas para fim de contextualização, compreendidas em cada categoria. Com base nessa lista, você deve definir APENAS A CATEGORIA de cada questão. Observe a lista abaixo:

{categories_with_subcategories}

A questão que você analisará terá:
- O texto base para a questão
- O enunciado da questão
- Quatro ou cinco alternativas, com indicações se são corretas ou incorretas
- A imagem da questão, caso exista (opcional)

Lembre-se que algumas dessas questões terão imagens, que você não poderá ver. Tente inferir o conteúdo da imagem com base no enunciado, quando possível.

Com base nessas questões, procure entender qual a categoria da questão. Responda APENAS com a categoria escolhida, exatamente como está na lista acima, seguida do grau de confiança, de 0 a 100% (não inclua o sinal de % na resposta), que você tem de que a categoria escolhida está correta.

Não responda com NENHUM tipo de detalhamento ou justificativa além de "Categoria escolhida;Grau de confiança".

A resposta DEVE seguir o formato: "Categoria escolhida;Grau de confiança". Exemplo: "Ética e Política;80".
Não use aspas e não sugira outras categorias além das listadas.
"""


SYSTEM_MESSAGE_SUBCATEGORY = """Você é um professor especializado em vestibulares e deve categorizar as questões que são enviadas a você.

As mensagens enviadas terão:
- Um enunciado
- O texto extraído da questão (opcional, pode estar em branco)
- Quatro ou cinco alternativas, com indicações se são corretas ou incorretas
- A imagem da questão, caso exista (opcional)

Com base nessas informações, você deve definir em que subcategoria está a questão, usando a lista de subcategorias abaixo. Tente responder considerando que tipos de conhecimento ou competências são avaliados na questão e os temas com que se relacionam. Escolha exatamente 1 subcategoria.

Responda apenas o nome da subcategoria escolhida, sem nenhum detalhamento ou justificativa.

Escreva a subcategoria exatamente como está, sem utilizar aspas. Se uma subcategoria contém conectivos como "e", como em "Lentes e Instrumentos", você deve considerar e responder toda a linha, nesse caso "Lentes e Instrumentos;Grau de confiança".

Escolha APENAS uma das subcategorias fornecidas na lista abaixo. Não responda com subcategorias não listadas aqui.

Responda com o nome da subcategoria seguida do grau de confiança, de 0 a 100% (não inclua o sinal de % na resposta), que você tem de que a subcategoria escolhida está correta. A resposta deve seguir o formato: "Subcategoria escolhida;Grau de confiança". Exemplo: "Lentes e Instrumentos;75".

Não responda NENHUMA OUTRA INFORMAÇÃO OU JUSTIFICATIVA além do nome da subcategoria escolhida e do grau de confiança.

Em caso de subcategorias com anos entre parênteses, exemplo: "Brasil Contemporâneo (1985 até hoje)", a resposta deve incluir toda subcategoria, nesse caso: "Brasil Contemporâneo (1985 até hoje);Grau de confiança"
As subcategorias disponíveis para a categoria selecionada são:
{subcategories}

"""


SYSTEM_MESSAGE_SUBJECT = """Você é um professor especializado em vestibulares e deve dizer qual a matéria da questão que é enviadas a você.
A mensagem enviada terá:
    - Um enunciado
    - O texto extraído da questão (opcional, pode estar em branco)
    - Quatro ou cinco alternativas, com indicações se são corretas ou incorretas
Com base nessas informações, você deve definir em que matéria está a questão, usando a lista de matérias abaixo. Tente responder considerando que tipos de conhecimento ou competências são avaliados na questão e os temas com que se relacionam. Escolha apenas uma matéria.
Responda apenas o nome da matéria escolhida, sem nenhum detalhamento ou justificativa.
Escreva SOMENTE matérias que estejam mencionadas a seguir, e nenhuma outra, sem utilizar aspas. As matérias disponíveis são:
{subjects}
"""


SYSTEM_MESSAGE_ANSWER = """Você é um professor especializado na correção de vestibulares e deve escrever resoluções comentadas das questões que são enviadas para você.
As mensagens enviadas terão:
    - Um enunciado
    - (Opcional) uma foto que complementa o enunciado
    - Quatro ou cinco alternativas, com indicações se são corretas ou incorretas
Com base nessas informações, você deve elaborar uma explicação concisa de por que a alternativa correta está correta e por que as demais estão erradas. Comente cada uma das alternativas incorretas e aponte o erro nelas. Por favor, seja minucioso nas suas análises e procure explicar detalhes específicos de cada alternativa quando necessário, sendo direto e conciso."""


SYSTEM_MESSAGE_ANSWER_DISCURSIVE = """Você é um professor especializado na correção de vestibulares e deve escrever resoluções comentadas das questões que são enviadas para você.
As mensagens enviadas terão:
    - Um enunciado
    - (Opcional) uma foto que complementa o enunciado
Com base nessas informações, você deve elaborar uma resposta concisa, mas com todos os detalhes essenciais para compreender a questão, para a questão discursiva que foi enviada.
"""


SYSTEM_MESSAGE_ANSWER_O1 = """Você é um professor especializado na correção de vestibulares e deve escrever resoluções comentadas das questões que são enviadas para você.
As mensagens enviadas terão:
    - Um enunciado
    - (Opcional) uma descrição da imagem que complementa o enunciado
    - Quatro ou cinco alternativas, com indicações se são corretas ou incorretas
Com base nessas informações, você deve elaborar uma explicação concisa de por que a alternativa correta está correta e por que as demais estão erradas. Comente cada uma das alternativas incorretas e aponte o erro nelas. Por favor, seja minucioso nas suas análises e procure explicar detalhes específicos de cada alternativa quando necessário, sendo direto e conciso."""


SYSTEM_MESSAGE_TEST = """Responda uma mensagem com o texto 'a' independente do que for lhe enviado. Responda APENAS 'a'."""


IMAGE_DESCRIPTION_SYSTEM_MESSAGE = """"Você recebeu a tarefa de gerar uma descrição de uma imagem que complementa um enunciado de uma questão de vestibular. Sua descrição será utilizada por um modelo de linguagem para ajudar a resolver essa questão. Para que o modelo possa entender a imagem sem visualizá-la, siga as seguintes instruções:

0. **Considere o enunciado e as alternativas da questão**: A descrição da imagem deve conter todas as informações que auxliem na resolução da questão.

1. **Descreva a imagem de forma detalhada**, mencionando todos os elementos visíveis: objetos, pessoas, paisagens, cores, posições e relações espaciais. Não se esqueça de incluir detalhes menores que possam ser relevantes para a questão.

2. **Inclua informações sobre o contexto**: Se a imagem envolve uma situação específica (ex.: uma cena histórica, fenômeno natural, experimento científico), explique o que está acontecendo e qual o foco principal da imagem.

3. **Especifique as características visuais de cada elemento**: Descreva as cores, texturas, formas, dimensões, expressões faciais (se houver pessoas), ou qualquer outro aspecto visual que ajude o modelo a entender a cena com clareza.

4. **Relacione os elementos da imagem**: Explique como os objetos ou elementos interagem entre si. Por exemplo, se uma pessoa está segurando um objeto, como ela o segura e qual é a relação espacial entre eles.

5. **Descreva a atmosfera e o tom da imagem**: Isso pode incluir elementos como iluminação (se é claro ou escuro), clima, ou emoções expressadas, caso sejam visíveis.

6. **Considere aspectos culturais, históricos ou científicos**, se forem aplicáveis, para dar mais contexto e ajudar na interpretação da imagem.

Seu objetivo é fornecer uma descrição completa e rica o suficiente para que o modelo de linguagem possa compreender e responder à questão apenas com base no que você escreveu. Evite suposições e mantenha a descrição objetiva."
"""


SYSTEM_MESSAGE_VALIDATION_ANSWER = """Você recebeu a tarefa de verificar se uma resposta para uma questão de vestibular está coerente. Para realizar essa verificação, siga as instruções abaixo:

1. **Leia atentamente o enunciado da questão, as alternativas e a resolução enviada.** A resolução deve ser uma explicação detalhada que justifique a resposta correta.

2. **Compare a resposta indicada como correta nas alternativas com a conclusão da resolução.** Se a resolução apresentar uma resposta diferente da que está marcada como correta nas alternativas, considere automaticamente que a resolução está incoerente e responda 'Não'.

3. **Verifique se a resolução justifica corretamente a resposta marcada como correta.** Isso significa que a explicação fornecida deve estar de acordo com o conteúdo da questão e levar logicamente à resposta correta.

4. **Certifique-se de que a resolução não contenha erros de raciocínio, fatos incorretos ou falhas na lógica.** Mesmo que a resolução leve à resposta correta, se o raciocínio estiver incorreto ou impreciso, a resposta deve ser 'Não'.

5. **Sua resposta final deve ser 'Sim' ou 'Não'.** Responda 'Sim' apenas se a resolução estiver totalmente coerente com a resposta correta e bem justificada. Caso contrário, responda 'Não'. Não forneça nenhuma explicação adicional.

Lembre-se: se houver qualquer discrepância entre a resposta destacada das alternativas e a conclusão da resolução, ou se a justificativa for incorreta ou insuficiente, responda 'Não'."""


SYSTEM_MESSAGE_VALIDATION_ANSWER_DISCURSIVE = """Você tem a tarefa de verificar a coerência de uma resposta discursiva para uma questão discurisva de vestibular. Siga as instruções detalhadas abaixo para realizar essa verificação:

1. **Analise o enunciado da questão e a resolução fornecida.** A resolução deve conter uma explicação detalhada que justifique a resposta fornecida.

2. **Avalie se a resolução justifica adequadamente a resposta fornecida.** A explicação deve estar alinhada com o conteúdo da questão e levar logicamente àquela resposta.

3. **Verifique a precisão e a lógica da resolução.** A resolução não deve conter erros de raciocínio, informações incorretas ou falhas lógicas. Mesmo que a resposta final esteja correta, a justificativa deve ser correta e completa.

4. **Sua resposta final deve ser apenas 'Sim' ou 'Não'.** Responda 'Sim' somente se a resolução estiver totalmente coerente com a resposta correta e for bem fundamentada. Caso contrário, responda 'Não'. Não forneça explicações adicionais.

OBS: Se a questão perguntar um valor numérico (que não seja uma expressão matemática em função de outras variáveis), a resposta deve indicar claramente o valor numérico. Caso contrário, responda 'Não'.
"""


DELATEXIFY_SYSTEM_MESSAGE = """Você recebeu a tarefa de remover todo Latex de um texto. Você deve substituir todas as expressões Latex por uma versão que pode ser renderizada como texto comum, usando símbolos e palavras. Se não houver Latex na mensagem, você deve devolver a mensagem original. Para operações matemáticas, priorize símbolos simples no lugar de palavras ao indicar operações, como em: "5 . 5" em vez de "5 vezes 5"."""


O1_PROMPT = """Instruções:
- Você é um corretor de exames especializado em vestibulares. Sua tarefa é
  escrever resoluções detalhadas para as questões que são enviadas a você.
- Cada mensagem enviada conterá:
  - Um enunciado
  - (Opcional) uma descrição da imagem que complementa o enunciado
  - Quatro ou cinco alternativas
  - A indicação da alternativa correta
- Com base nessas informações, escreva uma explicação concisa de por que a
  alternativa correta está correta e por que as demais estão erradas.
- Comente cada alternativa incorreta e aponte o erro específico em cada uma.
  Seja minucioso na sua análise, mas mantenha clareza e concisão.
- Retorne apenas a explicação da resposta no seu retorno.
- Não inclua nenhuma formatação adicional, como blocos de código markdown.
"""


O1_PROMPT_DISCURSIVE = """Instruções:
- Você é um corretor de exames especializado em vestibulares. Sua tarefa é
  escrever resoluções detalhadas para as questões discursivas que são enviadas a você.
- Cada mensagem enviada conterá:
  - Um enunciado
  - (Opcional) uma descrição da imagem que complementa o enunciado
- Com base nessas informações, escreva uma explicação concisa, mas com todos os
  detalhes essenciais para compreender a questão, para a questão discursiva que
  foi enviada.
- Retorne apenas a explicação da resposta no seu retorno.
- Não inclua nenhuma formatação adicional, como blocos de código markdown.
"""


SYSTEM_MESSAGE_GENERATE_DESCRIPTION_FROM_IMAGE = """Você recebeu a tarefa de gerar uma descrição completa de todos os conteúdos abordados em uma imagem de um caderno escolar.
A descrição deve ser feita de forma que seja possível inferir todo o conteúdo da imagem apenas com a descrição, sem a necessidade de visualizar a imagem.
Não responda com NENHUMA outra informação além da descrição completa da imagem. Foque no conteúdo anotado e não nas informações pessoais do aluno.
"""


SYSTEM_MESSAGE_GENERATE_QUESTIONS = """
Você é um assistente que gera questões de múltipla escolha para alunos de vestibular com base em descrições de imagens. As questões devem ser claras, objetivas e relacionadas ao conteúdo descrito. Responda em formato JSON (ou lista de dicionários) com os campos "text", "choices" (lista de strings) e "correct_choice" (letra da opção correta, ex: "A").
Exemplo de resposta:
[
    {
        "text": "Qual é a capital da França?",
        "choices": ["A) Paris", "B) Londres", "C) Berlim", "D) Madrid"],
        "correct_choice": "A"
    },
    ...
]
"""

SYSTEM_MESSAGE_CLASSIFY_DIFFICULTY = """
Você é um assistente que classifica questões de múltipla escolha dos vestibulares brasileiros com base em sua dificuldade. Para isso, considere APENAS o nível de raciocínio e esforço mental necessário para a resolução, e NÃO o tamanho do enunciado ou a quantidade de informações apresentadas.

"Fácil": Questões classificadas como Fácil podem exigir um nível de raciocínio, mas a resolução deve ser relativamente direta, sem necessidade de múltiplas etapas complexas. O estudante consegue chegar à resposta correta aplicando conceitos básicos ou diretos, usando fórmulas conhecidas, identificando padrões evidentes ou interpretando informações simples de textos, gráficos ou tabelas. **O tamanho do enunciado não deve influenciar a classificação: uma questão longa pode ser Fácil se a resolução for simples e intuitiva.**

"Média": Questões classificadas como Média exigem um grau intermediário de análise e encadeamento de ideias, mas sem chegar ao nível de desafios avançados. Essas questões não podem ser resolvidas de forma direta, mas também não exigem raciocínio aprofundado ou conhecimento especializado. Para ser classificada como Média, a questão deve envolver um equilíbrio entre compreensão e aplicação de conceitos, sem requerer inferências complexas, conexões inesperadas ou resolução prolongada.

"Difícil": Questões Difíceis exigem um nível elevado de raciocínio analítico, podendo envolver múltiplas etapas interdependentes, deduções não triviais ou conhecimentos que vão além do básico esperado para um aluno do ensino médio. Normalmente, demandam a correlação entre diferentes conteúdos, a aplicação de estratégias pouco óbvias ou um tempo significativo de resolução. Questões que abordam temas raros na base curricular ou apresentam armadilhas conceituais também devem ser classificadas como Difícil.

**Importante:** O critério principal para a classificação é a complexidade do raciocínio exigido para chegar à resposta, e NÃO o tamanho do enunciado ou a extensão do problema apresentado. Analise também as alternativas da questão, sua complexidade e a dificuldade de se chegar à resposta correta.

Responda APENAS com a dificuldade da questão, sem nenhuma pontuação ou comentário adicional. Julgue a dificuldade considerando que as questões analisadas têm como público-alvo alunos concluintes do ensino médio brasileiro.
"""


INPUT_FILE = "questions_to_verify.json"
OUTPUT_FILE = "classified.json"


CATEGORIES_WITH_SUBCATEGORIES = {
    "Português": [
        "Manifestações Culturais (Cultura Brasileira, Meios de Comunicação, História da Arte, Arte Contemporânea)",
        "Interpretação de Texto (Construção de Texto, Texto Publicitário, Texto Jornalístico, Fake News, Tipo Textual, Função da Linguagem)",
        "Texto Literário (Quinhentismo, Barroco, Arcadismo, Romantismo, Realismo, Naturalismo, Simbolismo, Parnasianismo, Modernismo, Prosa Contemporânea, Poesia Contemporânea, Teoria da Literatura)",
        "Domínio da Língua (Variedade Linguística, Conjunções e Conectivos, Denotação e Conotação, Pontuação, Figuras de Linguagem, Formação de Palavras, Gêneros Literários, Recursos de Estilo, Análise Sintática, Semântica e Vocabulário, Gramática)",
    ],
    "Matemática": [
        "Aritmética (Razão e Proporção, MMC e MDC, Matemática Financeira, Operações Básicas, Conjuntos e Sistemas, Álgebra Linear, Números Complexos)",
        "Análise de Dados (Transformações e Operações Matemáticas, Escala e Medidas de Grandeza, Gráficos e Tabelas, Média, Moda e Mediana, Lógica)",
        "Funções (Função Afim, Função Exponencial, Função Quadrática, Logaritmo, Classificação de Funções)",
        "Séries (Progressão Aritmética, Progressão Geométrica, Sequência Numérica)",
        "Probabilidade (Evento Único, Eventos Condicionais)",
        "Combinatória (Combinação, Arranjo, Permutação)",
        "Geometria (Trigonometria, Área e Volume, Geometria Plana, Geometria Espacial, Geometria Analítica)",
    ],
    "Física": [
        "Mecânica (Energia e Momento, Dinâmica, Estática, Cinemática, Fluídos)",
        "Termologia (Temperatura, Calorimetria, Termodinâmica, Gases, Dilatação)",
        "Ótica (Reflexão, Refração e Difração, Lentes e Instrumentos)",
        "Ondulatória (Ondas, Acústica, Movimento Harmônico (MHS))",
        "Física Moderna (Magnetismo e Indução Eletromagnética, Física Quântica, Relatividade)",
        "Análise Dimensional (Conversão de Unidades, Ordem de Grandeza)",
        "Eletromagnetismo (Circuitos Elétricos, Magnetismo, Energia Elétrica)",
    ],
    "Química": [
        "Propriedades Químicas (Modelos Atômicos, Tabela Periódica, Ligações Químicas, Polaridade e Geometria Molecular, Compostos Iônicos e Oxidantes)",
        "Propriedades da Matéria (Separação de Misturas, Densidade, Mudanças de Estado, Radioatividade)",
        "Química Inorgânica (Nomenclatura de Funções, Reações de Neutralização, Cátions e Ânions)",
        "Cálculo Químico (Estequiometria, Soluções, Equilíbrio Químico, Termoquímica)",
        "Química Orgânica (Cadeias Carbônicas, Nomenclatura de Funções Orgânicas, Isomeria, Polímeros, Reações Orgânicas, Bioquímica e Processos Celulares)",
        "Eletroquímica (Pilhas, Eletrólise, Reações de Oxirredução)",
    ],
    "Biologia": [
        "Parasitologia (Vírus, Bactérias, Protozoários)",
        "Saúde (Prevenção de Doenças, Nutrição)",
        "Ecologia (Relações Ecológicas, Sustentabilidade, Ciclos Biogeoquímicos, Evolução, Especiação, Cadeia Alimentar)",
        "Zoologia (Fisiologia Animal, Reprodução Animal, Evolução)",
        "Botânica (Fisiologia Vegetal, Reprodução Vegetal)",
        "Citologia (Respiração Celular, Divisão Celular, Organelas, Fotossíntese, Transporte Celular)",
        "Genética (DNA e RNA, Heredogramas, Probabilidade Genética)",
        "Anatomia Humana (Hormônios, Sistemas Vitais, Tecidos, Fisiologia Humana)",
    ],
    "Filosofia": [
        "Filosofia Antiga (Ciência e Conhecimento, Filosofia Política, Ética, Metafísica, Estética, Escolas Filosóficas)",
        "Filosofia Medieval (Filosofia e Religião, Metafísica, Renascimento)",
        "Filosofia Moderna (Ciência e Conhecimento, Filosofia Política, Ética, Metafísica, Estética)",
        "Filosofia Contemporânea (Ciência e Conhecimento, Filosofia Política, Ética, Metafísica, Estética, Existencialismo)",
    ],
    "História": [
        "História do Brasil (Brasil Colônia (1500-1822), Período Imperial (1822-1889), República Velha (1889-1930), Era Vargas (1930-1945), Quarta República (1945-1964), Regime Militar (1964-1985), Brasil Contemporâneo (1985 até hoje), Urbanização e Industrialização, Povos Originários)",
        "História das Ideias (Tecnologia e Sociedade, Arte e História, Conceitos Políticos, Museus e Memória, Iluminismo)",
        "História Global (Antiguidade Clássica, Idade Média, Idade Moderna, Era das Revoluções (1789-1848), Revoluções Industriais, Era do Imperialismo (1848-1914), Primeira Guerra Mundial, Período Entreguerras (1919-1939), Segunda Guerra Mundial, Guerra Fria, Genocídio e Direitos Humanos, Oriente Médio)",
        "História das Américas (América Pré-Colombiana, Colonização Espanhola, História dos Estados Unidos)",
    ],
    "Sociologia": [
        "Sociologia do Brasil (Cultura Brasileira, Pensadores Brasileiros)",
        "Movimentos Sociais (Questões de Gênero, Questões Raciais, Participação Política)",
        "Teóricos da Sociologia (Émile Durkheim, Max Weber, Marxismo, Escola de Frankfurt, Sociologia Contemporânea)",
    ],
    "Geografia": [
        "Homem e Natureza (Mudanças Climáticas, Espaço Agrário, Fontes de Energia)",
        "Geografia Física (Relevo, Geologia, Clima, Hidrografia)",
        "Geografia Humana (Tecnologia e Trabalho, Demografia, Globalização, Economia e Indústria, Renda e Desigualdade, Espaço Urbano, Política Internacional)",
        "Cartografia (Projeções Cartográficas, Mapas Temáticos, Elementos do Mapa)",
    ],
    "Inglês": [
        "Textos da Internet (Blogs, Redes Sociais, Artigos de Opinião, Sites Educativos, Fóruns de Discussão)",
        "Textos Literários (Contos, Poemas, Romances, Ensaios, Teatro)",
        "Textos Jornalísticos (Notícias, Reportagens, Editorial, Entrevistas, Colunas)",
        "Charges (Satíricas, Políticas, Econômicas, Sociais, Culturais)",
        "Vocabulário (Expressões Idiomáticas, Gírias, Palavras Formais, Palavras Informais, Frases Comuns)",
    ],
    "Espanhol": [
        "Textos da Internet (Blogs, Redes Sociais, Artigos de Opinião, Sites Educativos, Fóruns de Discussão)",
        "Textos Literários (Contos, Poemas, Romances, Ensaios, Teatro)",
        "Textos Jornalísticos (Notícias, Reportagens, Editorial, Entrevistas, Colunas)",
        "Charges (Satíricas, Políticas, Econômicas, Sociais, Culturais)",
        "Vocabulário (Expressões Idiomáticas, Gírias, Palavras Formais, Palavras Informais, Frases Comuns)",
    ],
}


CATEGORIES = {
    "Português": [
        "Manifestações Culturais",
        "Interpretação de Texto",
        "Texto Literário",
        "Domínio da Língua",
    ],
    "Matemática": [
        "Aritmética",
        "Análise de Dados",
        "Funções",
        "Séries",
        "Probabilidade",
        "Combinatória",
        "Geometria",
    ],
    "Física": [
        "Mecânica",
        "Termologia",
        "Ótica",
        "Ondulatória",
        "Física Moderna",
        "Análise Dimensional",
        "Eletromagnetismo",
    ],
    "Química": [
        "Propriedades Químicas",
        "Propriedades da Matéria",
        "Química Inorgânica",
        "Cálculo Químico",
        "Química Orgânica",
        "Eletroquímica",
    ],
    "Biologia": [
        "Parasitologia",
        "Saúde",
        "Ecologia",
        "Zoologia",
        "Botânica",
        "Citologia",
        "Genética",
        "Anatomia Humana",
    ],
    "Filosofia": [
        "Filosofia Antiga",
        "Filosofia Medieval",
        "Filosofia Moderna",
        "Filosofia Contemporânea",
    ],
    "História": [
        "História do Brasil",
        "História das Ideias",
        "História Global",
        "História das Américas",
    ],
    "Sociologia": [
        "Sociologia do Brasil",
        "Movimentos Sociais",
        "Teóricos da Sociologia",
    ],
    "Geografia": [
        "Homem e Natureza",
        "Geografia Física",
        "Geografia Humana",
        "Cartografia",
    ],
    "Inglês": [
        "Textos da Internet",
        "Textos Literários",
        "Textos Jornalísticos",
        "Charges",
        "Vocabulário",
    ],
    "Espanhol": [
        "Textos da Internet",
        "Textos Literários",
        "Textos Jornalísticos",
        "Charges",
        "Vocabulário",
    ],
}

SUBCATEGORIES = {
    "Manifestações Culturais": [
        "Cultura Brasileira",
        "Meios de Comunicação",
        "História da Arte",
        "Arte Contemporânea",
        "Variedade Linguística",
    ],
    "Interpretação de Texto": [
        "Construção de Texto",
        "Texto Publicitário",
        "Texto Jornalístico",
        "Tipo Textual",
        "Função da Linguagem",
        "Fake News",
    ],
    "Texto Literário": [
        "Quinhentismo",
        "Barroco",
        "Arcadismo",
        "Romantismo",
        "Realismo",
        "Naturalismo",
        "Simbolismo",
        "Parnasianismo",
        "Modernismo",
        "Prosa Contemporânea",
        "Poesia Contemporânea",
        "Teoria da Literatura",
    ],
    "Domínio da Língua": [
        "Variedade Linguística",
        "Conjunções e Conectivos",
        "Denotação e Conotação",
        "Pontuação",
        "Figuras de Linguagem",
        "Formação de Palavras",
        "Gêneros Literários",
        "Recursos de Estilo",
        "Análise Sintática",
        "Semântica e Vocabulário",
        "Gramática",
    ],
    "Aritmética": [
        "Razão e Proporção",
        "MMC e MDC",
        "Matemática Financeira",
        "Operações Básicas",
        "Conjuntos e Sistemas",
        "Álgebra Linear",
        "Números Complexos",
    ],
    "Análise de Dados": [
        "Transformações e Operações Matemáticas",
        "Escala e Medidas de Grandeza",
        "Gráficos e Tabelas",
        "Média, Moda e Mediana",
        "Lógica",
    ],
    "Funções": [
        "Função Afim",
        "Função Exponencial",
        "Função Quadrática",
        "Logaritmo",
        "Classificação de Funções",
    ],
    "Séries": ["Progressão Aritmética", "Progressão Geométrica", "Sequência Numérica"],
    "Probabilidade": ["Evento Único", "Eventos Condicionais"],
    "Combinatória": ["Combinação", "Arranjo", "Permutação"],
    "Geometria": [
        "Trigonometria",
        "Área e Volume",
        "Geometria Plana",
        "Geometria Espacial",
        "Geometria Analítica",
    ],
    "Mecânica": [
        "Energia e Momento",
        "Dinâmica",
        "Estática",
        "Cinemática",
        "Fluídos",
    ],
    "Termologia": [
        "Temperatura",
        "Calorimetria",
        "Termodinâmica",
        "Gases",
        "Dilatação",
    ],
    "Ótica": ["Reflexão", "Refração e Difração", "Lentes e Instrumentos"],
    "Ondulatória": ["Ondas", "Acústica", "Movimento Harmônico (MHS)"],
    "Física Moderna": [
        "Física Quântica",
        "Relatividade",
    ],
    "Análise Dimensional": ["Conversão de Unidades", "Ordem de Grandeza"],
    "Eletromagnetismo": ["Circuitos Elétricos", "Magnetismo", "Energia Elétrica"],
    "Propriedades Químicas": [
        "Modelos Atômicos",
        "Tabela Periódica",
        "Ligações Químicas",
        "Polaridade e Geometria Molecular",
        "Compostos Iônicos e Oxidantes",
    ],
    "Propriedades da Matéria": [
        "Separação de Misturas",
        "Densidade",
        "Mudanças de Estado",
        "Radioatividade",
    ],
    "Química Inorgânica": [
        "Nomenclatura de Funções",
        "Reações de Neutralização",
        "Cátions e Ânions",
    ],
    "Cálculo Químico": [
        "Estequiometria",
        "Soluções",
        "Equilíbrio Químico",
        "Termoquímica",
    ],
    "Química Orgânica": [
        "Cadeias Carbônicas",
        "Nomenclatura de Funções Orgânicas",
        "Isomeria",
        "Polímeros",
        "Reações Orgânicas",
        "Bioquímica e Processos Celulares",
    ],
    "Eletroquímica": [
        "Pilhas",
        "Eletrólise",
        "Reações de Oxirredução",
    ],
    "Parasitologia": ["Vírus", "Bactérias", "Protozoários"],
    "Saúde": ["Prevenção de Doenças", "Nutrição"],
    "Ecologia": [
        "Relações Ecológicas",
        "Sustentabilidade",
        "Ciclos Biogeoquímicos",
        "Evolução",
        "Especiação",
        "Cadeia Alimentar",
    ],
    "Zoologia": ["Fisiologia Animal", "Reprodução Animal", "Evolução"],
    "Botânica": ["Fisiologia Vegetal", "Reprodução Vegetal"],
    "Citologia": [
        "Respiração Celular",
        "Divisão Celular",
        "Organelas",
        "Fotossíntese",
        "Transporte Celular",
    ],
    "Genética": ["DNA e RNA", "Heredogramas", "Probabilidade Genética"],
    "Anatomia Humana": ["Hormônios", "Sistemas Vitais", "Tecidos", "Fisiologia Humana"],
    "Filosofia Antiga": [
        "Ciência e Conhecimento",
        "Filosofia Política",
        "Ética",
        "Metafísica",
        "Estética",
        "Escolas Filosóficas",
    ],
    "Filosofia Medieval": ["Filosofia e Religião", "Metafísica", "Renascimento"],
    "Filosofia Moderna": [
        "Ciência e Conhecimento",
        "Filosofia Política",
        "Ética",
        "Metafísica",
        "Estética",
    ],
    "Filosofia Contemporânea": [
        "Ciência e Conhecimento",
        "Filosofia Política",
        "Ética",
        "Metafísica",
        "Estética",
        "Existencialismo",
    ],
    "História do Brasil": [
        "Brasil Colônia (1500-1822)",
        "Período Imperial (1822-1889)",
        "República Velha (1889-1930)",
        "Era Vargas (1930-1945)",
        "Quarta República (1945-1964)",
        "Regime Militar (1964-1985)",
        "Brasil Contemporâneo (1985 até hoje)",
        "Urbanização e Industrialização",
        "Povos Originários",
    ],
    "História das Ideias": [
        "Tecnologia e Sociedade",
        "Arte e História",
        "Conceitos Políticos",
        "Museus e Memória",
        "Iluminismo",
    ],
    "História Global": [
        "Antiguidade Clássica",
        "Idade Média",
        "Idade Moderna",
        "Era das Revoluções (1789-1848)",
        "Revoluções Industriais",
        "Era do Imperialismo (1848-1914)",
        "Primeira Guerra Mundial",
        "Período Entreguerras (1919-1939)",
        "Segunda Guerra Mundial",
        "Guerra Fria",
        "Genocídio e Direitos Humanos",
        "Oriente Médio",
    ],
    "História das Américas": [
        "América Pré-Colombiana",
        "Colonização Espanhola",
        "História dos Estados Unidos",
    ],
    "Sociologia do Brasil": ["Cultura Brasileira", "Pensadores Brasileiros"],
    "Movimentos Sociais": [
        "Questões de Gênero",
        "Questões Raciais",
        "Participação Política",
    ],
    "Teóricos da Sociologia": [
        "Émile Durkheim",
        "Max Weber",
        "Marxismo",
        "Escola de Frankfurt",
        "Sociologia Contemporânea",
    ],
    "Homem e Natureza": ["Mudanças Climáticas", "Espaço Agrário", "Fontes de Energia"],
    "Geografia Física": ["Relevo", "Geologia", "Clima", "Hidrografia"],
    "Geografia Humana": [
        "Tecnologia e Trabalho",
        "Demografia",
        "Globalização",
        "Economia e Indústria",
        "Renda e Desigualdade",
        "Espaço Urbano",
        "Política Internacional",
    ],
    "Cartografia": ["Projeções Cartográficas", "Mapas Temáticos", "Elementos do Mapa"],
    "Textos da Internet": [
        "Blogs",
        "Redes Sociais",
        "Artigos de Opinião",
        "Sites Educativos",
        "Fóruns de Discussão",
    ],
    "Textos Literários": ["Contos", "Poemas", "Romances", "Ensaios", "Teatro"],
    "Textos Jornalísticos": [
        "Notícias",
        "Reportagens",
        "Editorial",
        "Entrevistas",
        "Colunas",
    ],
    "Charges": ["Satíricas", "Políticas", "Econômicas", "Sociais", "Culturais"],
    "Vocabulário": [
        "Expressões Idiomáticas",
        "Gírias",
        "Palavras Formais",
        "Palavras Informais",
        "Frases Comuns",
    ],
}

SUBCATEGORIES_TO_PARENT_CATEGORIES: dict[str, str] = {}
for parent_category, subcategories in SUBCATEGORIES.items():
    for subcategory in subcategories:
        SUBCATEGORIES_TO_PARENT_CATEGORIES[subcategory] = parent_category


# Define custom exceptions for retries
class APICallError(Exception):
    pass


total_tokens = 0
errors = 0
low_confidence_cases = 0

question_exclude_list = []

logger = logging.getLogger(__name__)


# @shared_task(rate_limit="1/s")
def add_number(question_id: int):
    question = Question.objects.get(id=question_id)
    question.text = question.text + str(question_id)
    question.save()


def encode_image(image_file):
    return base64.b64encode(image_file.read()).decode("utf-8")


def call_extract_openai(base64_image: str) -> str:
    """
    Helper function that takes a file-like object, encodes the image, and calls the OpenAI API.
    """
    try:
        response = openai_utils.get_completion(
            "gpt-4o",
            0,
            [
                {
                    "role": "system",
                    "content": SYSTEM_MESSAGE_GENERATE_DESCRIPTION_FROM_IMAGE,
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Essa é minha foto:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": base64_image,
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            json_mode=False,
            timeout=30,
        )
        if not response:
            raise ValueError("Resposta vazia da API do OpenAI.")
        return response
    except Exception as e:
        logger.error(f"Error in call_extract_openai: {e}")
        raise


# def generate_pdf_for_questions(questions, file_path):
#     doc = SimpleDocTemplate(file_path, pagesize=letter)
#     elements = []
#     styles = getSampleStyleSheet()

#     for question in questions:
#         if question.category and question.subcategory:
#             extra_embedding_text = question.extra_embedding_text or "N/A"
#             question_text = question.text or "N/A"
#             choices = [choice.text for choice in question.choices.all()]
#             category = question.category or "N/A"
#             subcategory = question.subcategory or "N/A"

#             elements.append(
#                 Paragraph(
#                     f"<b>Extra Embedding Text:</b> {extra_embedding_text}",
#                     styles["Normal"],
#                 )
#             )
#             elements.append(Spacer(1, 12))
#             elements.append(
#                 Paragraph(f"<b>Question Text:</b> {question_text}", styles["Normal"])
#             )
#             elements.append(Spacer(1, 12))
#             elements.append(Paragraph("<b>Choices:</b>", styles["Normal"]))
#             for choice in choices:
#                 elements.append(Paragraph(f" - {choice}", styles["Normal"]))
#             elements.append(Spacer(1, 12))
#             elements.append(Paragraph(f"<b>Category:</b> {category}", styles["Normal"]))
#             elements.append(Spacer(1, 12))
#             elements.append(
#                 Paragraph(f"<b>Subcategory:</b> {subcategory}", styles["Normal"])
#             )
#             elements.append(Spacer(1, 24))  # Add extra space between questions

#     print("\n\n\nGerando PDF\n\n\n")
#     doc.build(elements)


def all_questions_categorized():
    return (
        Question.objects.filter(source="UERJ 2024")
        .exclude(category="")
        .exclude(subcategory="")
        .count()
        > 50
    )


acertos = 0


# @shared_task(bind=True, max_retries=3)
def classify_difficulty(self, question_id: int) -> None:
    try:
        global acertos
        question = Question.objects.prefetch_related("choices").get(id=question_id)
        choices = (
            [choice.text for choice in question.choices.all()]
            if question.choices.exists()
            else None
        )

        difficulty = process_question_classify_difficulty(
            question.text,
            question.extra_embedding_text,
            choices,
            question.image.url if question.image else "",
            is_retry=False,
        )

        if difficulty not in ["Fácil", "Média", "Difícil"]:
            process_question_classify_difficulty(
                question.text,
                question.extra_embedding_text,
                choices,
                question.image.url if question.image else "",
                is_retry=True,
            )

        logger.info(
            f"\n\nDificuldade original da questão {question_id}: {question.difficulty}"
        )
        logger.info(
            f"Dificuldade classificada da questão {question_id}: {difficulty}\n\n"
        )

        if question.difficulty and question.difficulty == difficulty:
            acertos += 1
            logger.info(f"Total de acertos até agora: {acertos}")

        question.difficulty = difficulty
        question.save()

    except (BadRequestError, RateLimitError) as exc:
        try:
            self.retry(countdown=10, exc=exc)
        except MaxRetriesExceededError:
            raise Exception(f"Max retries exceeded for question {question_id}")
    except Exception as e:
        raise Exception(f"Error processing question {question_id}: {e}")


def process_question_classify_difficulty(
    question_text: str,
    extra_text: str,
    choices: list[str] | None,
    image_url: str,
    is_retry: bool = False,
) -> str:
    system_message = SYSTEM_MESSAGE_CLASSIFY_DIFFICULTY

    user_message = (
        (
            "Texto extraído: {}\n\nEnunciado:\n{}\n\nAlternativas:\n{}".format(
                extra_text, question_text, "\n".join(choices)
            )
        )
        if choices
        else "Texto extraído: {}\n\nEnunciado:\n{}".format(extra_text, question_text)
    )

    if is_retry:
        system_message = (
            SYSTEM_MESSAGE_CLASSIFY_DIFFICULTY
            + "\n\nA resposta deve estar entre as opções: 'Fácil', 'Média', 'Difícil'."
        )

    messages = [
        {"role": "system", "content": system_message},
        {
            "role": "user",
            "content": (
                [
                    {"type": "text", "text": user_message},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "high"},
                    },
                ]
                if image_url
                else user_message
            ),
        },
    ]

    response = openai_utils.get_completion("gpt-4o", 0.2, messages, False, 30)

    return response.content


# @shared_task(bind=True)
def validate_category_and_subcategory(self, question_id: int) -> str:
    """
    Função que envia a questão de múltipla escolha, categoria e subcategoria ao modelo gpt-4o-mini para validação.
    Retorna 'Sim' ou 'Não'.
    """
    # Buscar a questão com prefetch das choices
    question = Question.objects.prefetch_related("choices").get(id=question_id)

    # Verificar se a questão é de múltipla escolha
    if not question.choices.exists():
        raise ValueError(f"Questão {question.id} não é de múltipla escolha.")

    # Preparar as alternativas (choices) para inclusão na mensagem
    choices_text = "\n".join(
        [f"{i + 1}) {choice.text}" for i, choice in enumerate(question.choices.all())]
    )

    system_message = SYSTEM_MESSAGE_VALIDATION.format(
        question_extra_embedding_text=question.extra_embedding_text,
        question_text=question.text,
        category=question.category,
        subcategory=question.subcategory,
        choices=choices_text,
    )

    messages = [{"role": "system", "content": system_message}]

    response = openai_utils.get_completion(
        "gpt-4o-mini", 0.0, messages, False, 10
    ).content

    if response not in ["sim", "não"]:
        raise ValueError(f"Resposta inválida do GPT: {response}")

    if response == "não":
        logger.debug(f"Questão {question_id} de {question.source}: Não")

    return response


# @shared_task(bind=True, max_retries=5)
def categorize_question(self, question_id: int, temperature: float = 0):
    try:
        question = Question.objects.prefetch_related("choices").get(id=question_id)
        choices = [choice.text for choice in question.choices.all()]

        # Ignorar questões discursivas (sem alternativas)
        if not choices:
            logger.info(f"Ignorando questão discursiva: {question_id}")
            return

        # Gerar URL completo da imagem se existir
        # image_url = question.image.url.replace("/media/", "") if question.image else ""
        # full_image_url = S3_BUCKER_PREFIX + image_url if image_url else ""

        image_url = question.image.url if question.image else ""

        # Categorização
        category, confidence = process_question_classify_category(
            question.text,
            question.extra_embedding_text,
            choices,
            str(question.id),
            question.subject,
            question.source,
            temperature,
            image_url,  # Envie a URL da imagem
        )

        # Subcategorização
        subcategory, _ = process_question_classify_subcategory(
            question.text,
            question.extra_embedding_text,
            choices,
            str(question.id),
            category,
            temperature,
            image_url,  # Envie a URL da imagem
        )

        # Salvando a categoria e subcategoria no banco de dados
        question.category = category
        question.subcategory = subcategory
        question.save()

        # Verifica se todas as questões foram categorizadas e gera o PDF
        # if all_questions_categorized():
        #     questions = (
        #         Question.objects.filter(source="UERJ 2024")
        #         .exclude(category="")
        #         .exclude(subcategory="")
        #     )
        #     generate_pdf_for_questions(questions, "uerj_2024_questions.pdf")

        return

    except (BadRequestError, RateLimitError) as exc:
        try:
            temperature += 0.1
            global errors
            self.retry(countdown=10, exc=exc, kwargs={"temperature": temperature})
            errors += 1
        except MaxRetriesExceededError:
            raise Exception(f"Max retries exceeded for question {question_id}")
    except Exception as e:
        raise Exception(f"Error processing question {question_id}: {e}")


def process_question_classify_category(
    question_text: str,
    extra_text: str,
    choices: list[str],
    question_pk: str,
    subject: str,
    source: str,
    temperature: float,
    image_url: str = "",  # Adicione o parâmetro da URL da imagem
) -> tuple[str, float]:
    try:
        categories = "\n".join(CATEGORIES_WITH_SUBCATEGORIES[subject])
        system_message = SYSTEM_MESSAGE_CATEGORY.format(
            categories_with_subcategories=categories
        )

        user_message = (
            "Texto extraído: {}\n\nEnunciado:\n{}\n\nAlternativas:\n{}".format(
                extra_text, question_text, "\n".join(choices)
            )
        )

        # Se a URL da imagem estiver disponível, inclua-a na mensagem
        messages = [
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": (
                    [
                        {"type": "text", "text": user_message},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url, "detail": "low"},
                        },
                    ]
                    if image_url
                    else user_message
                ),
            },
        ]

        # Chamada da API (GPT-4o-mini)
        response = openai_utils.get_completion(
            "gpt-4o-mini", temperature, messages, False, 10
        )

        # Contabilização dos tokens usados
        global total_tokens
        total_tokens += response.tokens_used

        ai_response = response.content

        if not ai_response:
            raise ValueError("Empty response from GPT")

        # Separar categoria e grau de confiança
        category, confidence_str = ai_response.split(";")
        confidence = float(confidence_str)

        # Se a confiança for menor que 80%, tentar novamente com o GPT-4o
        if confidence < 80:
            logger.warning(
                f"Baixa confiança ({confidence}%) para a questão {question_pk} de {source}. Tentando novamente com GPT-4o."
            )
            global low_confidence_cases
            low_confidence_cases += 1

            response = openai_utils.get_completion(
                "gpt-4o", temperature, messages, False, 10
            )

            # Contabilização dos tokens usados após o retry
            total_tokens += response.tokens_used
            logger.debug(f"Total tokens after retry: {total_tokens}")

            ai_response = response.content
            category, confidence_str = ai_response.split(";")
            confidence = float(confidence_str)

        # Verificação final da categoria
        if category in CATEGORIES[subject]:
            return category, confidence
        else:
            # Solicitar nova resposta
            error_message = f"A resposta '{category}' está fora das categorias esperadas. Por favor, responda com uma das categorias fornecidas na lista."
            messages.append({"role": "user", "content": error_message})
            global errors
            errors += 1

            response = openai_utils.get_completion(
                "gpt-4o", temperature, messages, False, 10
            )

            # Contabilização dos tokens usados após a segunda tentativa
            total_tokens += response.tokens_used
            logger.debug(f"Total tokens after second retry: {total_tokens}")

            ai_response = response.content

            category, confidence_str = ai_response.split(";")
            if not category or category not in CATEGORIES[subject]:
                raise ValueError(f"Invalid category response after retry: {category}")

            return category, confidence

    except BadRequestError as e:
        logger.warning(f"BadRequestError: {e}, Source: {source}")
        raise
    except RateLimitError as e:
        logger.warning(f"RateLimitError: {e}, Source: {source}")
        raise
    except Exception as e:
        logger.warning(f"Error: {e}, Source: {source}")
        raise


def process_question_classify_subcategory(
    question_text: str,
    extra_text: str,
    choices: list[str],
    question_pk: str,
    category: str,
    temperature: float,
    image_url: str = "",  # Adicione o parâmetro da URL da imagem
) -> tuple[str, float]:
    try:
        subcategories = "\n".join(SUBCATEGORIES[category])
        system_message = SYSTEM_MESSAGE_SUBCATEGORY.format(subcategories=subcategories)

        user_message = (
            "Texto extraído: {}\n\nEnunciado:\n{}\n\nAlternativas:\n{}".format(
                extra_text, question_text, "\n".join(choices)
            )
        )

        # Se a URL da imagem estiver disponível, inclua-a na mensagem
        messages = [
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": (
                    [
                        {"type": "text", "text": user_message},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url, "detail": "low"},
                        },
                    ]
                    if image_url
                    else user_message
                ),
            },
        ]

        # Chamada da API (GPT-4o-mini)
        response = openai_utils.get_completion(
            "gpt-4o-mini", temperature, messages, False, 10
        )

        # Contabilização dos tokens usados
        global total_tokens
        total_tokens += response.tokens_used

        logger.debug(f"Total tokens: {total_tokens}")

        ai_response = response.content

        if not ai_response:
            raise ValueError("Empty response from GPT")

        # Separar subcategoria e grau de confiança
        subcategory, confidence_str = ai_response.split(";")
        confidence = float(confidence_str)

        # Se a confiança for menor que 80%, tentar novamente com o GPT-4o
        if confidence < 80:
            logger.warning(
                f"Baixa confiança ({confidence}%) para a questão {question_pk}. Tentando novamente com GPT-4o."
            )
            global low_confidence_cases
            low_confidence_cases += 1

            response = openai_utils.get_completion(
                "gpt-4o", temperature, messages, False, 10
            )

            # Contabilização dos tokens usados após o retry
            total_tokens += response.tokens_used
            logger.debug(f"Total tokens after retry: {total_tokens}")

            ai_response = response.content
            subcategory, confidence_str = ai_response.split(";")
            confidence = float(confidence_str)

        # Verificação final da subcategoria
        if subcategory in SUBCATEGORIES[category]:
            return subcategory, confidence
        else:
            # Solicitar nova resposta
            error_message = f"A resposta '{subcategory}' está fora das subcategorias esperadas. Por favor, responda com uma das subcategorias fornecidas na lista."
            messages.append({"role": "user", "content": error_message})
            global errors
            errors += 1

            response = openai_utils.get_completion(
                "gpt-4o", temperature, messages, False, 10
            )

            # Contabilização dos tokens usados após a segunda tentativa
            total_tokens += response.tokens_used
            logger.debug(f"Total tokens after second retry: {total_tokens}")

            ai_response = response.content

            subcategory, confidence_str = ai_response.split(";")
            if not subcategory or subcategory not in SUBCATEGORIES[category]:
                raise ValueError(
                    f"Invalid subcategory response after retry: {subcategory}"
                )

            return subcategory, confidence

    except BadRequestError as e:
        logger.warning(f"BadRequestError: {e}")
        raise
    except RateLimitError as e:
        logger.warning(f"RateLimitError: {e}")
        raise
    except Exception as e:
        logger.warning(f"Error: {e}")
        raise


"""@shared_task(bind=True, max_retries=5)
def generate_answer(self, question_id: int, temperature: float = 0):
    try:
        question = Question.objects.prefetch_related("choices").get(id=question_id)

        if question.answer_text:
            logger.info(f"Answer already generated for question {question_id}")
            return

        choices = [choice.text for choice in question.choices.all()]
        correct_choice = next(
            (choice.text for choice in question.choices.all() if choice.is_correct),
            "Não informada",
        )

        image_url = question.image.url if question.image else ""

        # First attempt to generate the answer
        answer_text = generate_answer_for_question(
            question.text,
            question.extra_embedding_text,
            choices,
            correct_choice,
            question.subject,
            temperature,
            image_url,
        )

        # Process delatexify result, raise error if delatexify fails
        answer_text_delatexified = delatexify(answer_text)
        if not answer_text_delatexified:
            raise ValueError(
                f"Empty response from GPT during first delatexification for question {question_id}"
            )

        image_description = (
            generate_image_description(
                image_url, question.text, choices, correct_choice, temperature
            )
            if image_url
            else ""
        )

        question_text_with_image = (
            f"{image_description}\n\n{question.extra_embedding_text}"
            if image_description
            else question.extra_embedding_text
        )

        # Validate the generated answer
        validation_response = validate_resolution(
            question.text,
            question_text_with_image,
            answer_text_delatexified,
            choices,
            correct_choice,
            question.subject,
            temperature,
        )

        # If validation suggests the answer might be wrong, generate image description and try again
        if validation_response and "não" in validation_response.lower():

            new_answer_text = generate_answer_for_question_o1(
                question.text,
                question_text_with_image,
                choices,
                correct_choice,
                question.subject,
            )

            # Delatexify the new answer, raise error if it fails
            answer_text_delatexified = delatexify(new_answer_text)
            if not answer_text_delatexified:
                raise ValueError(
                    f"Empty response from GPT during second delatexification for question {question_id}"
                )

            final_validation_response = validate_resolution(
                question.text,
                question_text_with_image,
                answer_text_delatexified,
                choices,
                correct_choice,
                question.subject,
                temperature,
            )

            if final_validation_response and "não" in final_validation_response.lower():
                logger.warning(
                    f"Final validation still suggests the answer might be wrong for question {question_id}"
                )
                return

        # Save the final answer
        question.answer_text = answer_text_delatexified
        question.save()

        return

    except (BadRequestError, RateLimitError) as exc:
        try:
            temperature += 0.1  # Gradually increase the temperature
            self.retry(countdown=10, exc=exc, kwargs={"temperature": temperature})
        except MaxRetriesExceededError:
            raise Exception(f"Max retries exceeded for question {question_id}")

    except ValueError as ve:
        # Handle ValueError specifically if needed (e.g., log it or notify the user)
        logger.error(
            f"ValueError in generating answer for question {question_id}: {ve}"
        )
        raise

    except Exception as e:
        raise Exception(f"Error processing question {question_id}: {e}")"""


# @shared_task(bind=True, max_retries=5)
def generate_answer(self, question_id: int, temperature: float = 0):
    try:
        question = Question.objects.prefetch_related("choices").get(id=question_id)

        if question.answer_text or question.answer_image:
            logger.info(f"Answer already generated for question {question_id}")
            return

        if question.choices.exists():
            handle_multiple_choice(question, temperature)
        else:
            handle_discursive(question, temperature)

    except (BadRequestError, RateLimitError) as exc:
        try:
            temperature += 0.1  # Gradually increase the temperature
            self.retry(countdown=10, exc=exc, kwargs={"temperature": temperature})
        except MaxRetriesExceededError:
            raise Exception(f"Max retries exceeded for question {question_id}")

    except ValueError as ve:
        logger.error(
            f"ValueError in generating answer for question {question_id}: {ve}"
        )
        raise

    except Exception as e:
        raise Exception(f"Error processing question {question_id}: {e}")


def handle_multiple_choice(question, temperature):
    choices = [choice.text for choice in question.choices.all()]
    correct_choice = next(
        (choice.text for choice in question.choices.all() if choice.is_correct),
        "Não informada",
    )
    image_url = question.image.url if question.image else ""

    answer_text = generate_multiple_choice_answer(
        question, choices, correct_choice, temperature, image_url
    )

    if answer_text:
        # Save the answer within a transaction to ensure atomicity
        with transaction.atomic():
            question.answer_text = answer_text
            question.save()


def handle_discursive(question, temperature):
    answer_text = generate_discursive_answer(question, temperature)

    if answer_text:
        # Save the answer within a transaction to ensure atomicity
        with transaction.atomic():
            question.answer_text = answer_text
            question.save()


def generate_multiple_choice_answer(
    question, choices, correct_choice, temperature, image_url
):
    # Initial answer generation
    answer_text = generate_answer_text_for_multiple_choice_question(
        question.text,
        question.extra_embedding_text,
        choices,
        correct_choice,
        question.subject,
        temperature,
        image_url,
    )

    answer_text_delatexified = delatexify(answer_text)
    if not answer_text_delatexified:
        raise ValueError(f"Empty response from GPT for question {question.id}")

    image_description = (
        generate_image_description(
            image_url, question.text, choices, correct_choice, temperature
        )
        if image_url
        else ""
    )

    question_text_with_image = (
        f"{image_description}\n\n{question.extra_embedding_text}"
        if image_description
        else question.extra_embedding_text
    )

    validation_response = validate_resolution(
        question.text,
        question_text_with_image,
        answer_text_delatexified,
        choices,
        correct_choice,
        question.subject,
        temperature,
    )

    if validation_response and "não" in validation_response.lower():
        logger.info(f"Validation failed, retrying for question {question.id}")
        # Retry with higher temperature or alternative strategy
        new_answer_text = generate_answer_for_question_o1(
            question.text,
            question_text_with_image,
            choices,
            correct_choice,
            question.subject,
        )

        # Delatexify the new answer, raise error if it fails
        answer_text_delatexified = delatexify(new_answer_text)
        if not answer_text_delatexified:
            raise ValueError(
                f"Empty response from GPT during second delatexification for question {question.id}"
            )

        final_validation_response = validate_resolution(
            question.text,
            question_text_with_image,
            answer_text_delatexified,
            choices,
            correct_choice,
            question.subject,
            temperature,
        )

        if final_validation_response and "não" in final_validation_response.lower():
            logger.warning(
                f"Final validation still suggests the answer might be wrong for question {question.id}"
            )
            return

    return answer_text_delatexified


def generate_discursive_answer(question, temperature=0.1):
    image_url = question.image.url if question.image else ""

    answer_text = generate_answer_text_for_discursive_question(
        question.text,
        question.extra_embedding_text,
        question.subject,
        temperature,
        image_url,
    )

    answer_text_delatexified = delatexify(answer_text)
    if not answer_text_delatexified:
        raise ValueError(f"Empty response from GPT for question {question.id}")

    image_description = (
        generate_image_description(
            image_url=image_url,
            question_text=question.text,
            alternatives=None,
            correct_alternative=None,
            temperature=temperature,
        )
        if image_url
        else ""
    )

    question_text_with_image = (
        f"{image_description}\n\n{question.extra_embedding_text}"
        if image_description
        else question.extra_embedding_text
    )

    validation_response = validate_resolution(
        question.text,
        question_text_with_image,
        answer_text_delatexified,
        None,
        None,
        question.subject,
        temperature,
    )

    if validation_response and "não" in validation_response.lower():
        logger.info(f"Validation failed, retrying for question {question.id}")
        # Retry with higher temperature or alternative strategy
        new_answer_text = generate_answer_for_question_o1(
            question.text,
            question_text_with_image,
            None,
            None,
            question.subject,
        )

        # Delatexify the new answer, raise error if it fails
        answer_text_delatexified = delatexify(new_answer_text)
        if not answer_text_delatexified:
            raise ValueError(
                f"Empty response from GPT during second delatexification for question {question.id}"
            )

        final_validation_response = validate_resolution(
            question.text,
            question_text_with_image,
            answer_text_delatexified,
            None,
            None,
            question.subject,
            temperature,
        )

        if final_validation_response and "não" in final_validation_response.lower():
            logger.warning(
                f"Final validation still suggests the answer might be wrong for question {question.id}"
            )
            return

    return answer_text_delatexified


def generate_answer_text_for_multiple_choice_question(
    question_text: str,
    extra_embedding_text: str,
    choices: list[str],
    correct_choice: str,
    subject: str,
    temperature: float = 0,
    image_url: str = "",
):
    try:
        system_message = SYSTEM_MESSAGE_ANSWER
        user_message = "Texto extraído: {}\n\nEnunciado:\n{}\n\nAlternativas:\n{}\n\nAlternativa correta: {}".format(
            extra_embedding_text, question_text, "\n".join(choices), correct_choice
        )

        # Log message before the API call
        logger.info(
            f"Iniciando chamada para gerar resposta para a questão: {question_text[:20]}..."
        )
        # Se a URL da imagem estiver disponível, inclua-a na mensagem
        messages = [
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": (
                    [
                        {"type": "text", "text": user_message},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url, "detail": "low"},
                        },
                    ]
                    if image_url
                    else user_message
                ),
            },
        ]

        response = openai_utils.get_completion(
            "gpt-4o", temperature, messages, False, 30
        )

        logger.info(
            f"GPT answer generation successful for question {question_text[:20]}..."
        )

        global total_tokens
        total_tokens += response.tokens_used

        logger.debug(f"Total tokens: {total_tokens}")

        ai_response = response.content

        if not ai_response:
            raise ValueError("Empty response from GPT")

        return ai_response

    except BadRequestError as e:
        logger.warning(f"BadRequestError: {e}")
        raise
    except RateLimitError as e:
        logger.warning(f"RateLimitError: {e}")
        raise


def generate_answer_for_question_o1(
    question_text: str,
    question_text_with_image: str,
    choices: list[str] | None,
    correct_choice: str | None,
    subject: str,
):
    try:
        if choices and correct_choice:
            user_message = (
                O1_PROMPT
                + "\n\nDescrição da imagem (opcional): {}\n\nEnunciado:\n{}\n\nAlternativas:\n{}\n\nAlternativa correta: {}".format(
                    question_text_with_image,
                    question_text,
                    "\n".join(choices),
                    correct_choice,
                )
            )
        else:
            user_message = (
                O1_PROMPT_DISCURSIVE
                + "\n\nDescrição da imagem (opcional): {}\n\nEnunciado:\n{}".format(
                    question_text_with_image, question_text
                )
            )

        logger.info(
            f"Iniciando chamada para gerar novamente (o1) a resposta para a questão: {question_text[:20]}..."
        )

        messages = [
            {"role": "user", "content": user_message},
        ]
        temperature = 1

        response = openai_utils.get_completion(
            "o1-mini", temperature, messages, False, 10
        )

        ai_response = response.content

        if not ai_response:
            raise ValueError("Empty response from GPT")

        logger.info(
            f"GPT o1-mini new answer generation successful for question {question_text[:20]}..."
        )

        global total_tokens
        total_tokens += response.tokens_used

        logger.debug(f"Total tokens: {total_tokens}")

        return ai_response

    except BadRequestError as e:
        logger.warning(f"BadRequestError: {e}")
        raise
    except RateLimitError as e:
        logger.warning(f"RateLimitError: {e}")
        raise


def generate_answer_text_for_discursive_question(
    question_text: str,
    extra_embedding_text: str,
    subject: str,
    temperature: float = 0,
    image_url: str = "",
):
    try:
        system_message = SYSTEM_MESSAGE_ANSWER_DISCURSIVE
        user_message = "Texto extraído: {}\n\nEnunciado:\n{}".format(
            extra_embedding_text, question_text
        )

        logger.info(
            f"Iniciando chamada para gerar resposta para a questão: {question_text[:20]}..."
        )

        # Se a URL da imagem estiver disponível, inclua-a na mensagem
        messages = [
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": (
                    [
                        {"type": "text", "text": user_message},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url, "detail": "high"},
                        },
                    ]
                    if image_url
                    else user_message
                ),
            },
        ]

        response = openai_utils.get_completion(
            "gpt-4o", temperature, messages, False, 30
        )

        logger.info(
            f"GPT answer generation successful for question {question_text[:20]}..."
        )

        global total_tokens
        total_tokens += response.tokens_used

        logger.debug(f"Total tokens: {total_tokens}")

        ai_response = response.content

        if not ai_response:
            raise ValueError("Empty response from GPT")

        return ai_response

    except BadRequestError as e:
        logger.warning(f"BadRequestError: {e}")
        raise
    except RateLimitError as e:
        logger.warning(f"RateLimitError: {e}")
        raise


def generate_image_description(
    image_url: str,
    question_text: str,
    alternatives: list[str] | None,
    correct_alternative: str | None,
    temperature: float = 0,
):
    try:
        if alternatives and correct_alternative:
            alternatives_formatted = "\n".join(
                f"{i + 1}. {alt}" for i, alt in enumerate(alternatives)
            )
            user_message = f"""Essa é a imagem da questão.

Enunciado: {question_text}

Alternativas:
{alternatives_formatted}

Alternativa correta: {correct_alternative}
"""
        else:
            user_message = f"""Essa é a imagem da questão.

Enunciado: {question_text}
"""

        system_message = IMAGE_DESCRIPTION_SYSTEM_MESSAGE
        messages = [
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "high"},
                    },
                ],
            },
        ]

        response = openai_utils.get_completion(
            "gpt-4o", temperature, messages, False, 30
        )

        ai_response = response.content

        logger.info(
            f"GPT image description generation successful for question {question_text[:20]}..."
        )

        if not ai_response:
            raise ValueError("Empty response from GPT")

        return ai_response

    except BadRequestError as e:
        logger.warning(f"BadRequestError: {e}")
        raise
    except RateLimitError as e:
        logger.warning(f"RateLimitError: {e}")
        raise
    except Exception as e:
        logger.warning(f"Error: {e}")
        raise


def validate_resolution(
    question_text: str,
    question_text_with_image: str,
    answer_text: str,
    choices: list[str] | None,
    correct_choice: str | None,
    subject: str,
    temperature: float = 0,
):
    try:
        if choices and correct_choice:
            system_message = SYSTEM_MESSAGE_VALIDATION_ANSWER
            user_message = "Texto extraído: {}\n\nEnunciado:\n{}\n\nAlternativas:\n{}\n\nAlternativa correta: {}\n\nResolução:\n{}".format(
                question_text_with_image,
                question_text,
                "\n".join(choices),
                correct_choice,
                answer_text,
            )
        else:
            system_message = SYSTEM_MESSAGE_VALIDATION_ANSWER_DISCURSIVE
            user_message = (
                "Texto extraído: {}\n\nEnunciado:\n{}\n\nResolução:\n{}".format(
                    question_text_with_image,
                    question_text,
                    answer_text,
                )
            )

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        response = openai_utils.get_completion(
            "gpt-4o-mini", temperature, messages, False, 10
        )

        ai_response = response.content

        if not ai_response:
            raise ValueError("Empty response from GPT")

        return ai_response

    except BadRequestError as e:
        logger.warning(f"BadRequestError: {e}")
        raise
    except RateLimitError as e:
        logger.warning(f"RateLimitError: {e}")
        raise
    except Exception as e:
        logger.warning(f"Error: {e}")
        raise


def delatexify(text):
    system_message = DELATEXIFY_SYSTEM_MESSAGE
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": text},
    ]

    logger.info(
        f"Iniciando chamada à API OpenAI para delatexificar a questão: {text[:20]}..."
    )
    # Make synchronous API call
    response = openai_utils.get_completion("gpt-4o-mini", 0, messages, False, 30)
    logger.info(f"GPT delatexify call successful for question {text[:20]}...")

    ai_response = response.content

    return ai_response


# @shared_task(bind=True, max_retries=5)
def generate_questions_from_images(
    self,
    base64_images: list[str],
    source: str,
    subject: str,
    extra_instructions: str,
    questions_per_image: int,
):
    """
    Função principal da tarefa que processa uma lista de imagens codificadas em base64 para gerar perguntas.
    """
    try:
        for index, base64_image in enumerate(base64_images, start=1):
            logger.info(f"Processando imagem {index}/{len(base64_images)}")

            # Passo 1: Gerar descrição da imagem
            description = describe_image(base64_image)
            if not description:
                logger.warning(f"Nenhuma descrição retornada para a imagem {index}")
                continue

            # Passo 2: Gerar perguntas com base na descrição
            questions = generate_questions_from_description(
                description, extra_instructions, questions_per_image
            )
            if not questions:
                logger.warning(f"Nenhuma pergunta gerada para a imagem {index}")
                continue

            # Passo 3: Salvar perguntas no banco de dados
            for question_data in questions:
                try:
                    with transaction.atomic():
                        # Criar o objeto Question
                        question = Question.objects.create(
                            text=question_data.get("text"),
                            source=source,
                            subject=subject,
                            is_active=False,  # So it doent show up in standard quizzes
                        )

                        # Criar as opções de resposta
                        choices = question_data.get("choices", [])
                        correct_choice_letter = question_data.get("correct_choice")

                        for choice in choices:
                            # Supondo que as opções estão no formato "A) Texto"
                            if ")" in choice:
                                choice_letter, choice_text = choice.split(")", 1)
                                choice_letter = choice_letter.strip().upper()
                                choice_text = choice_text.strip()

                                is_correct = (
                                    choice_letter == correct_choice_letter.upper()
                                )

                                question.choices.create(
                                    text=choice_text, is_correct=is_correct
                                )
                                logger.info(
                                    f"Opção '{choice_letter}' criada com sucesso para a pergunta ID {question.id}"
                                )

                        logger.info(
                            f"Pergunta ID {question.id} criada com sucesso para a imagem {index}"
                        )

                except Exception as e:
                    logger.error(
                        f"Erro ao salvar a pergunta para a imagem {index}: {e}"
                    )

    except (BadRequestError, RateLimitError) as e:
        logger.warning(f"Erro na API: {e}. Tentando novamente em 10 segundos...")
        self.retry(exc=e, countdown=10)
    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
        raise


def describe_image(base64_image: str) -> str:
    """
    Gera uma descrição para uma única imagem usando o GPT.
    """
    try:
        description = call_extract_openai(base64_image)
        return description

    except (BadRequestError, RateLimitError) as e:
        logger.warning(f"Erro na API em describe_image: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro em describe_image: {e}")
        raise


def parse_gpt_response(ai_response: str) -> list:
    """
    Extrai e retorna a lista de perguntas a partir da resposta do GPT.
    Remove os delimitadores de bloco de código se presentes.
    """
    try:
        # Padrão para capturar conteúdo dentro de blocos de código Markdown (com ou sem a especificação de linguagem)
        pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        match = re.search(pattern, ai_response, re.DOTALL)

        if match:
            json_str = match.group(1)
            logger.debug("Conteúdo JSON extraído do bloco de código.")
        else:
            # Se não houver delimitadores de bloco de código, assume que é JSON puro
            json_str = ai_response
            logger.debug(
                "Nenhum bloco de código encontrado. Usando a resposta inteira como JSON."
            )

        # Remover possíveis espaços em branco no início e no fim
        json_str = json_str.strip()

        # Decodificar o JSON
        questions = json.loads(json_str)

        return questions
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao parsear o JSON das perguntas: {e}")
        logger.debug(f"Resposta recebida do GPT após limpeza: {json_str}")
        raise ValueError("Formato de resposta inválido do GPT para perguntas")
    except Exception as e:
        logger.error(f"Erro inesperado ao parsear a resposta do GPT: {e}")
        raise


def generate_questions_from_description(
    description: str, extra_instructions: str, num_questions: int
) -> list[dict[str, Any]]:
    """
    Gera questões de múltipla escolha com base em uma descrição fornecida usando o GPT.
    """
    try:
        user_message = (
            "Você é um assistente que gera questões de múltipla escolha com 4 alternativas para alunos de vestibular"
            "com base em um conteúdo descrito. As questões devem ser claras, objetivas e relacionadas"
            "ao conteúdo descrito. Não mencione diretamente a imagem, mas sim o conteúdo dela. Responda **APENAS** uma LISTA de dicionários com os campos "
            "'text', 'choices' (lista de strings) e 'correct_choice' (letra da opção correta, ex: 'A').\n\n"
            "Exemplo de resposta:\n"
            "[\n"
            "    {\n"
            '        "text": "Qual é a capital da França?",\n'
            '        "choices": ["A) Paris", "B) Londres", "C) Berlim", "D) Madrid"],\n'
            '        "correct_choice": "A"\n'
            "    },\n"
            "    ...\n"
            "]\n\n"
            f"Com base no seguinte conteúdo, gere {num_questions} questões de múltipla escolha. "
            "Responda em formato JSON com os campos 'text', 'choices' (lista de strings) e "
            "'correct_choice' (letra da opção correta, ex: 'A').\n\n"
            f"Descrição: {description}\n\n"
        )

        if extra_instructions:
            user_message += f"\n\nInstruções extras: {extra_instructions}"

        logger.info(
            f"Iniciando chamada para gerar perguntas com o GPT: {description[:20]}..."
        )

        content = [
            {"type": "text", "text": user_message},
        ]

        messages = [
            {"role": "user", "content": content},
        ]
        temperature = 1

        response = openai_utils.get_completion(
            "o1-preview", temperature, messages, False, 60
        )

        ai_response = response.content

        if not ai_response:
            raise ValueError("Resposta vazia das perguntas pelo GPT")

        # Utilizar a função de parsing atualizada
        questions = parse_gpt_response(ai_response)

        # Validação básica do formato
        for q in questions:
            assert "text" in q
            assert "choices" in q
            assert "correct_choice" in q
        return questions
    except (json.JSONDecodeError, AssertionError) as e:
        logger.error(f"Erro ao parsear o JSON das perguntas: {e}")
        logger.debug(f"Resposta recebida do GPT após limpeza: {ai_response}")
        raise ValueError("Formato de resposta inválido do GPT para perguntas")
    except (BadRequestError, RateLimitError) as e:
        logger.warning(f"Erro na API em generate_questions_from_description: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro em generate_questions_from_description: {e}")
        raise


async def process_question_classify_subject(
    area: str,
    question_text: str,
    extra_text: str,
    choices: list[str],
) -> str:
    try:
        subjects = ENEM_AREAS[area]
        system_message = SYSTEM_MESSAGE_SUBJECT.format(subjects="\n".join(subjects))
        user_message = (
            "Texto extraído: {}\n\nEnunciado:\n{}\n\nAlternativas:\n{}".format(
                extra_text, question_text, "\n".join(choices)
            )
        )
        response = await openai_utils.get_completion(
            "gpt-4o-mini",
            0,
            [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            False,
            20,
        )
        global total_tokens
        total_tokens += response.tokens_used
        logger.debug(f"Total tokens: {total_tokens}")
        ai_response = response.content

        if ai_response:
            if ai_response in subjects:
                return ai_response
            raise ValueError(f"Invalid subject from response: {ai_response}")
        else:
            raise ValueError("Empty response from GPT")
    except BadRequestError as e:
        logger.warning(f"[italic red]BadRequestError: {e}[/italic red]")
        raise
    except RateLimitError as e:
        logger.warning(f"[italic red]RateLimitError: {e}[/italic red]")
        raise
    except Exception as e:
        logger.warning(f"[italic red]Error: {e}[/italic red]")
        raise


# @shared_task(bind=True)
def rerun_embeddings(self, question_id: int):
    question = Question.objects.prefetch_related("choices").get(id=question_id)
    embedding = openai_utils.compute_embedding(question.full_text_with_categories)
    question.embedding = embedding
    question.save()


""" async def process_question_classify(
    output_file: str | None,
    question_text: str,
    extra_text: str,
    choices: list[str],
    question_pk: str,
    source: str,
    subject: str,
):
    try:
        system_message = SYSTEM_MESSAGE.format(
            categories="\n".join(CATEGORIES[subject])
        )
        user_message = (
            "Texto extraído: {}\n\nEnunciado:\n{}\n\nAlternativas:\n{}".format(
                extra_text, question_text, "\n".join(choices)
            )
        )
        messages = [
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": user_message,
            },
        ]
        response = openai_utils.get_completion(
            "gpt-4o-mini", 0.5, messages
        )
        global total_tokens
        total_tokens += response.tokens_used
        print(f"Total tokens: {total_tokens}")
        ai_response = response.content
        print(f"Question {question_pk} completed: {ai_response}\n\n\n")
        # Save the completion immediately after getting it
        if ai_response:
            if ai_response in CATEGORIES[subject]:
                save_completion(output_file, question_pk, source, subject, ai_response)
                return
            elif len(ai_response.split(";")) == 2:
                category1, category2 = ai_response.split(";")
                if (
                    category1 in CATEGORIES[subject]
                    and category2 in CATEGORIES[subject]
                ):
                    save_completion(
                        output_file, question_pk, source, subject, ai_response
                    )
                    return
            print(f"\n\n[italic red]GPT ERROU A QUESTÃO {question_pk}[/italic red]\n\n")
            save_completion(
                output_file,
                question_pk,
                source,
                subject,
                "ERRO DO GPT CATEGORIAS RUINS: " + str(ai_response),
            )
            return
        else:
            print(f"\n\n[italic red]GPT ERROU A QUESTÃO {question_pk}[/italic red]\n\n")
            save_completion(
                output_file,
                question_pk,
                source,
                subject,
                "ERRO DO GPT CATEGORIA RUIM: " + str(ai_response),
            )
            return
    except BadRequestError as e:
        print(f"[italic red]BadRequestError: {e}[/italic red]")
        return
    except RateLimitError as e:
        print(f"[italic red]RateLimitError: {e}[/italic red]")
        return
    except Exception as e:
        print(f"[italic red]Error: {e}[/italic red]")
        save_completion(
            output_file,
            question_pk,
            source,
            subject,
            "ERRO DO GPT outra Exception: " + str(e),
        )
        return """


def save_completion(
    output_file: str, question_pk: str, source: str, subject: str, category: str
):
    """Save a single completion to a JSON file."""
    try:
        with open(output_file, "r") as f:
            completions = json.load(f)
    except FileNotFoundError:
        completions = []

    completions.append(
        {question_pk: {"source": source, "subject": subject, "category": category}}
    )

    with open(OUTPUT_FILE, "w") as f:
        json.dump(completions, f, indent=4)


def load_data(input_file):
    """Load data from a JSON file."""
    try:
        with open(input_file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


async def classify_category_for_questions(
    questions: list, choices: list, output_file: str | None
):
    tasks = []
    if output_file:
        completions = load_data(output_file)
    else:
        completions = []
    for question in questions:
        question_pk = str(question["pk"])
        if all(question_pk not in completion for completion in completions):
            question_text = question["fields"]["text"]
            extra_text = question["fields"]["extra_embedding_text"]
            subject = question["fields"]["subject"]
            choices = [
                choice["fields"]["text"]
                + (
                    " - Alternativa correta"
                    if choice["fields"]["is_correct"]
                    else " - Alternativa incorreta"
                )
                for choice in choices
                if choice["model"] == "core.choice"
                and choice["fields"]["question"] == question["pk"]
            ]
            task = asyncio.create_task(
                process_question_classify_category(
                    question_text,
                    extra_text,
                    choices,
                    question_pk,
                    subject,
                )
            )
            tasks.append(task)
            await asyncio.sleep(0.1)
            logger.debug(f"{len(tasks)} tasks na lista")
    return await asyncio.gather(*tasks)


async def classify_subject_for_questions(area: str, questions: list[dict]) -> list[str]:
    tasks = []
    for question in questions:
        question_text = question["question"]
        choices = question["choices"]
        task = asyncio.create_task(
            process_question_classify_subject(
                area,
                question_text,
                question["context"],
                choices,
            )
        )
        tasks.append(task)
        await asyncio.sleep(0.1)
        logger.debug(f"{len(tasks)} tasks na lista")
    return await asyncio.gather(*tasks)


def update_urls_from_orm(sql_results: list[dict[str, Any]], model_class: Any) -> None:
    """
    If you try to grab urls directly from SQL, you'll get urls without the prefix.
    This function updates SQL results with full URLs for a session.
    Assumes that the SQL results follow the format:
    {
        "id": <session_id>,
        "questions_and_answers": [
            {
                "id": <question_id>,
                "image": '',
                "answer_image": '',
                "video_url": '',
                "choices": [
                    {
                        "id": <choice_id>,
                        "image": '',
                    },
                    ...
                ],
            },
            ...
        ],
    }
    """
    session_ids = [item["id"] for item in sql_results]

    session_questions_prefetch = models.Prefetch(
        "session_question_set",
        queryset=SessionQuestion.objects.prefetch_related("question__choices"),
        to_attr="session_questions",
    )
    orm_objects = model_class.objects.filter(id__in=session_ids).prefetch_related(
        session_questions_prefetch
    )

    # Build URL mappings from ORM objects
    question_urls = {}
    choice_urls = {}
    for obj in orm_objects:
        for session_question in getattr(obj, "session_questions", []):
            question = session_question.question
            if question.id not in question_urls:
                question_urls[question.id] = {
                    "answer_image": question.answer_image or "",
                    "image": question.image or "",
                    "video_url": question.video_url,
                }
            for choice in question.choices.all():
                if choice.id not in choice_urls:
                    choice_urls[choice.id] = {
                        "image": choice.image or "",
                    }

    # Update SQL results with URL mappings
    for item in sql_results:
        questions_and_answers = item.get("questions_and_answers") or []
        for question in questions_and_answers:
            qid = question.get("id")
            if qid in question_urls:
                question.update(question_urls[qid])
            for choice in question.get("choices", []):
                cid = choice.get("id")
                if cid in choice_urls:
                    choice.update(choice_urls[cid])
