from typing import ClassVar

from openai import NOT_GIVEN, NotGiven
from openai.types.responses import (
    ResponseInputMessageContentListParam,
    ResponseInputParam,
)
from openai.types.shared_params.reasoning import Reasoning
from pydantic import BaseModel

from app.shared.prompts import Prompt, StructuredPrompt

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


class GenerateMinorTagsForTopic(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5-mini"

    def build_input(self, topic: str) -> ResponseInputParam:
        return [
            {
                "role": "system",
                "content": SYSTEM_MESSAGE_GENERATE_MINOR_TAGS_FOR_TOPIC,
            },
            {"role": "user", "content": f"Tópico: {topic}"},
        ]


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


class ClassifyTopicSubject(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5-mini"

    def build_input(self, subjects: list[str], topic: str) -> ResponseInputParam:
        return [
            {
                "role": "system",
                "content": SYSTEM_MESSAGE_CLASSIFY_TOPIC_SUBJECT.format(
                    subjects=chr(10).join(subjects)
                ),
            },
            {"role": "user", "content": f"Tópico: {topic}"},
        ]


# ---------------------------------------------
# Question generation from a user topic
# ---------------------------------------------

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


class QuestionInstance(BaseModel):
    text: str
    choices: list[str]
    correct_choice: str


class QuestionSet(BaseModel):
    questions: list[QuestionInstance]


class GenerateQuestionsFromTopic(StructuredPrompt[QuestionSet]):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5"

    def response_model(self):
        return QuestionSet

    def build_input(
        self, requires_math: bool, n_questions: int, topic: str, extra_instructions: str
    ) -> ResponseInputParam:
        system_message = (
            SYSTEM_MESSAGE_QUESTION_GENERATION_THEME_MATH
            if requires_math
            else SYSTEM_MESSAGE_QUESTION_GENERATION_THEME
        )
        user_message = f"Crie {n_questions} questões sobre: {topic}"
        if extra_instructions:
            user_message += f"\n\nInstruções adicionais: {extra_instructions}"
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]


# ---------------------------------------------
# Additional prompts used across flows/services
# ---------------------------------------------

SYSTEM_MESSAGE_IS_QUANTITATIVE = """
Você é um assistente que classifica questões de vestibular quanto à necessidade de usar papel para a resolução.
Objetivo Decidir se a questão PRECISA DE PAPEL PARA SER RESOLVIDA por um candidato típico do ensino médio, sem calculadora.

Como decidir (considere o caminho correto mais simples disponível): PRECISA DE PAPEL (true) quando houver pelo menos um dos seguintes:
•	Cálculos aritméticos de múltiplas etapas ou pesados (ex.: multiplicações/divisões com 3+ dígitos; somas de várias frações com denominadores distintos; potências/raízes não triviais; sistemas de equações; equações quadráticas não fatoráveis de imediato; probabilidades com várias combinações).
•	Manipulação algébrica, geométrica ou trigonométrica extensa (várias transformações, isolamentos, substituições ou identidades).
•	Necessidade de construir desenhos, gráficos, esquemas ou tabelas auxiliares para organizar casos/valores (árvores de probabilidade, diagramas auxiliares, esboços geométricos, tabelas).
•	Conferência de alternativas que exige contas extensas em mais de uma opção.
•	Extração de dados de gráficos/tabelas que demande cálculos precisos ou interpolação não trivial.
NÃO PRECISA DE PAPEL (false) quando:
•	A questão é conceitual/teórica ou de definição/identificação direta.
•	Exige apenas contas mentais curtas e estáveis (somas/subtrações simples; multiplicações pequenas; percentuais imediatos; comparação de ordens de grandeza; estimativas rápidas, Bhaskara resolvível com números inteiros e método de soma e produto).
•	É de interpretação de texto e/ou leitura de gráficos/figuras já fornecidos sem cálculos não triviais.
•	A eliminação/validação das alternativas pode ser feita por raciocínio qualitativo ou por uma única verificação numérica simples.
Regras gerais
•	Considere um estudante médio, sem calculadora ou ferramentas externas.
•	Baseie-se unicamente no enunciado fornecido; não invente dados, métodos ou passos não indicados/necessários.
•	Se houver mais de uma abordagem, adote a solução correta mentalmente mais viável; não imponha métodos mais difíceis do que o necessário.
•	Não mencione, cite ou reproduza o enunciado ou qualquer fonte interna; use-o apenas como base.
Saída: Responda APENAS "true" se precisa de papel ou "false" caso contrário. Não inclua explicações ou comentários adicionais. Uma única palavra em minúsculas, em linha única.
"""


class IsQuantitative(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "high"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5"

    def build_input(
        self,
        *,
        question_text_with_choices: str,
        image_urls: list[str] | None = None,
    ) -> ResponseInputParam:
        if image_urls:
            user_content: ResponseInputMessageContentListParam = [
                {"type": "input_text", "text": question_text_with_choices}
            ]
            user_content.extend(
                [
                    {
                        "type": "input_image",
                        "image_url": image_url,
                        "detail": "high",
                    }
                    for image_url in image_urls
                ]
            )
            return [
                {"role": "system", "content": SYSTEM_MESSAGE_IS_QUANTITATIVE},
                {"role": "user", "content": user_content},
            ]
        return [
            {"role": "system", "content": SYSTEM_MESSAGE_IS_QUANTITATIVE},
            {"role": "user", "content": question_text_with_choices},
        ]


SYSTEM_MESSAGE_MAJOR_TAG = """
Você é um professor especializado em vestibulares e deve classificar a matéria da questão recebida.
A mensagem incluirá:
•	Enunciado
•	Texto extraído (opcional, pode estar em branco)
•	Quatro ou cinco alternativas, com indicações se são corretas ou incorretas

Tarefa:
•	Com base nessas informações, determine em qual matéria a questão se enquadra, considerando as competências centrais necessárias para resolvê-la (conceitos, métodos, habilidades).
•	Escolha apenas uma matéria dentre a lista fornecida em {subjects}.
•	Se a questão for interdisciplinar, selecione a matéria predominante (a que mais dirige a resolução).
•	Se houver matérias semelhantes na lista, escolha a opção exatamente como aparece na lista (mesma grafia e acentuação).

Formato de resposta obrigatório:
•	Responda apenas com o nome da matéria escolhido exatamente como ele aparece na lista.
•	Sem aspas, sem comentários, sem linhas extras, sem espaços antes/depois.
Matérias disponíveis:
{subjects}
"""


class ClassifyQuestionSubject(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5-mini"

    def build_input(
        self,
        *,
        subjects: list[str],
        question_text_with_choices: str,
        image_urls: list[str] | None = None,
    ) -> ResponseInputParam:
        system_message = SYSTEM_MESSAGE_MAJOR_TAG.format(subjects="\n".join(subjects))
        user_message = f"""
Texto extraído: 

{question_text_with_choices}
"""
        if image_urls:
            user_content: ResponseInputMessageContentListParam = [
                {"type": "input_text", "text": user_message}
            ]
            for image_url in image_urls:
                user_content.append(
                    {"type": "input_image", "image_url": image_url, "detail": "low"}
                )
            return [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_content},
            ]
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]


SYSTEM_MESSAGE_GENERATE_MINOR_TAGS_FROM_QUESTION = """
Você é um especialista em gerar tags de conteúdo para questões de vestibular.
Você receberá o enunciado e as alternativas de uma questão específica e deverá gerar tags que identifiquem os tópicos centrais específicos abordados.
Instruções
•\tAnalise cuidadosamente enunciado e alternativas; não invente temas não sustentados pelo texto.
•\tEscolha de 1 a 3 tags que melhor representem os tópicos centrais (evite temas periféricos).
•\tSeja específico (prefira "Porcentagem", "Citologia", "Leitura de gráfico" a termos muito amplos como "Matemática", "Biologia", "Interpretação").
•\tEvite redundância: não repita tags nem use sinônimos muito próximos na mesma resposta.
•\tUse termos curtos e canônicos (1-3 palavras por tag)
•\tIdioma das tags: produza-as no mesmo idioma do enunciado da questão.
•\tSe o insumo estiver incompleto, assuma o mínimo necessário e escolha a(s) tag(s) mais geral(is) possível(is) que ainda representem o conteúdo; não invente detalhes.

Formato de resposta obrigatório
•\tRetorne APENAS as tags separadas por vírgula (ex.: Tag1, Tag2, Tag3).
•\tDe 1 a 3 tags por questão.
•\tSem pontuação adicional, aspas, explicações ou qualquer texto extra.
"""


class GenerateMinorTagsFromQuestion(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5-mini"

    def build_input(
        self,
        *,
        question_text_with_choices: str,
        image_urls: list[str] | None = None,
    ) -> ResponseInputParam:
        user_message = f"""
Questão completa:
{question_text_with_choices}

Analise a questão e identifique as tags mais apropriadas.
"""
        if image_urls:
            user_content: ResponseInputMessageContentListParam = [
                {"type": "input_text", "text": user_message}
            ]
            for image_url in image_urls:
                user_content.append(
                    {"type": "input_image", "image_url": image_url, "detail": "low"}
                )
            return [
                {
                    "role": "system",
                    "content": SYSTEM_MESSAGE_GENERATE_MINOR_TAGS_FROM_QUESTION,
                },
                {"role": "user", "content": user_content},
            ]
        return [
            {
                "role": "system",
                "content": SYSTEM_MESSAGE_GENERATE_MINOR_TAGS_FROM_QUESTION,
            },
            {"role": "user", "content": user_message},
        ]


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


class GenerateBlockTitle(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5-mini"

    def build_input(self, *, block_text: str) -> ResponseInputParam:
        return [
            {"role": "system", "content": SYSTEM_MESSAGE_BLOCK_TITLE},
            {"role": "user", "content": block_text},
        ]


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


class GenerateTitleFromTranscriptions(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5-mini"

    def build_input(self, *, titles_text: str) -> ResponseInputParam:
        return [
            {
                "role": "system",
                "content": SYSTEM_MESSAGE_GENERATE_TITLE_FROM_TRANSCRIPTIONS,
            },
            {"role": "user", "content": f"Títulos das transcrições:\n{titles_text}"},
        ]


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


class CheckMathInvolvementFromTitlesOrTopic(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5-mini"

    def build_input(self, *, block_titles: list[str]) -> ResponseInputParam:
        return [
            {"role": "system", "content": SYSTEM_MESSAGE_CHECK_MATH_INVOLVEMENT},
            {
                "role": "user",
                "content": f"{block_titles}",
            },
        ]


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
•	Macrotema vs. subtema: para temas amplos (ex.: "Matemática", "Biologia"), questões da área tendem a pontuar 4-5; para subtemas específicos (ex.: "Funções exponenciais"), exija aderência ao subtema para 4-5.
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


class VerifyQuestionPertinenceToTopic(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5-mini"

    def build_input(
        self,
        *,
        topic: str,
        question_text_with_choices: str,
        image_urls: list[str] | None = None,
    ) -> ResponseInputParam:
        content_text = "\n\n".join(
            [f"Topic: {topic}", f"Question and Choices: {question_text_with_choices}"]
        )
        if image_urls:
            user_content: ResponseInputMessageContentListParam = [
                {"type": "input_text", "text": content_text}
            ]
            for image_url in image_urls:
                user_content.append(
                    {
                        "type": "input_image",
                        "image_url": image_url,
                        "detail": "high",
                    }
                )
            return [
                {
                    "role": "system",
                    "content": SYSTEM_MESSAGE_QUESTION_PERTINENCE_TO_TOPIC,
                },
                {"role": "user", "content": user_content},
            ]
        return [
            {"role": "system", "content": SYSTEM_MESSAGE_QUESTION_PERTINENCE_TO_TOPIC},
            {"role": "user", "content": content_text},
        ]


SYSTEM_MESSAGE_GENERATE_INSTITUTION_DISPLAY_NAME = """You are an expert at producing concise, user-friendly display names for Brazilian educational institutions while preserving their core identity and recognition.

CORE PRINCIPLE: Preserve the institution's recognizable identity and meaning while shortening very long formal names into a clearly recognizable label when appropriate.

Heuristics to apply (use these as decision rules):
- If the official name is short (3 words or fewer) or already clearly recognizable, just return it with the right formatting, without any changes.
- If the official name is long (more than 5 words) or contains long generic phrases such as "Escola de Educação Básica e Profissional", "Centro Universitário das Faculdades", or "Instituto Federal de Educação, Ciência e Tecnologia de ...", extract the most distinctive, recognizable entity (often the sponsoring organization or the unique noun phrase). Example: "Escola de Educação Básica e Profissional da Fundação Bradesco" → "Fundação Bradesco". In some cases, those names might compose recognizable acronyms, like "UFRJ" or "UFMG" - in which case you should return the acronym.
- Preserve personal names and unique identifiers; if the name is primarily a person's name, keep the personal name and shorten surrounding titles (e.g. "Escola Estadual Professor João Silva" → "E.E. Prof. João Silva").
- Preserve names that indicate the institution's location (e.g. "Colégio Santo Agostinho Leblon -> Santo Agostinho Leblon").
- Avoid producing ambiguous or lossy abbreviations. Prefer clarity over aggressive shortening.
- Keep short, distinctive names intact (e.g. "Escola Parque" should remain "Escola Parque", not "Parque").
- If the name begins with "Escola Estudual" always abbreviate it to "E.E."
- When the acronym is NOT famous, use the full name. (eg. FASAVIC - FACULDADE SANTO AGOSTINHO DE VITÓRIA DA CONQUISTA (FASAVIC)	-> FASAVIC - Faculdade Santo Agostinho Vitória da Conquista)

Examples:
- "Universidade de São Paulo" → "USP" (universally known)
- "Fundação Getúlio Vargas - São Paulo" → "FGV - SP"
- "Escola de Educação Básica e Profissional da Fundação Bradesco" → "Fundação Bradesco"
- "Escola Parque" → "Escola Parque"
- "Colégio Santo Agostinho" → "Colégio Santo Agostinho" (keep if already short and meaningful)
- "Universidade Católica de Brasília" → "UCB" (if widely known) OR "Univ. Católica de Brasília" (if abbreviation not common)


Formatting:
- Return ONLY the display name as a single string, no explanation, no punctuation or extra characters.
- Aim for under 60 characters, up to 80 only if necessary to preserve identity.
"""


class GenerateInstitutionDisplayName(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = NOT_GIVEN
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5-nano"

    def build_input(self, *, full_name: str) -> ResponseInputParam:
        return [
            {
                "role": "system",
                "content": SYSTEM_MESSAGE_GENERATE_INSTITUTION_DISPLAY_NAME,
            },
            {"role": "user", "content": full_name},
        ]


# ---------------------------------------------
# Question generation from a transcription block
# ---------------------------------------------

SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION = """
Você é um assistente que gera questões de múltipla escolha no estilo dos grandes vestibulares brasileiros com 4 alternativas, com base em um conteúdo transcrito.

Você vai receber um bloco curto de transcrição que faz parte de um material maior. Use esse bloco como base de conteúdo; com base no que você encontrar, entenda se trata-se de um artigo, resumo, livro texto ou outro formato. Se for um resumo ou livro texto, não cite ou reproduza literalemente a transcrição - o objetivo deve ser identificar se o usuário entendeu o conteúdo explicado. Se for um artigo com marcas autorais, você pode fazer perguntas citando o material base (mas não só). 

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

Você vai receber um bloco curto de transcrição que faz parte de um material maior. Use esse bloco como base de conteúdo; com base no que você encontrar, entenda se trata-se de um artigo, resumo, livro texto ou outro formato. Se for um resumo ou livro texto, não cite ou reproduza literalemente a transcrição - o objetivo deve ser identificar se o usuário entendeu o conteúdo explicado. Se for um artigo com marcas autorais, você pode fazer perguntas citando o material base (mas não só). 

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


class GenerateQuestionsFromBlock(StructuredPrompt[QuestionSet]):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5"

    def response_model(self):
        return QuestionSet

    def build_input(
        self,
        requires_math: bool,
        block_text: str,
        n_questions: int,
        extra_instructions: str,
    ) -> ResponseInputParam:
        system_message = (
            SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION_MATH
            if requires_math
            else SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION
        )
        user_message = f"Com base no seguinte conteúdo, crie {n_questions} questões:\n\n{block_text}"
        if extra_instructions:
            user_message += f"\n\nInstruções adicionais: {extra_instructions}"
        return [
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": user_message,
            },
        ]


# ---------------------------------------------
# Answer generation for a given question (with optional images)
# ---------------------------------------------


class GenerateAnswer(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "high"}
    temperature: ClassVar[float | None | NotGiven] = NOT_GIVEN

    def model(self) -> str:
        return "gpt-5"

    def build_input(
        self,
        *,
        question_text_with_choices: str,
        correct_choice_letter: str,
        image_urls: list[str] | None = None,
    ) -> ResponseInputParam:
        system_message = """
Você é um professor especializado na correção de vestibulares e deve escrever resoluções comentadas das questões enviadas para você.

A entrada sempre conterá:
•\tUm enunciado.
•\tOpcionalmente, uma ou mais imagens que complementam o enunciado.
•\tQuatro ou cinco alternativas, cada uma com indicação se é correta ou incorreta.

Sua tarefa é produzir uma explicação direta e concisa que:
•\tJustifique por que a alternativa marcada como correta está correta.
•\tExplique por que cada alternativa marcada como incorreta está errada, comentando individualmente cada uma e apontando o erro específico (conceito equivocado, dado contraditório, condição ausente, interpretação inválida etc.).

Diretrizes:
•\tUtilize as informações do enunciado e da imagem; não invente fatos.
•\tSe houver imagem, integre as evidências relevantes mencionadas na descrição para sustentar a análise, sem copiar a descrição literalmente.
•\tUtilize conteúdo a nível de ensino médio e faculdade para justificar as respostas, considerando o que é sabido acerca dos temas abordados na questão.
•\tSiga rigorosamente as indicações de correta/incorreta fornecidas; não altere o gabarito. Se houver inconsistência clara entre o enunciado e as marcações, sinalize brevemente e adote a interpretação mais plausível.
•\tSeja específico: aponte trechos, ideias ou condições nas alternativas que justificam o acerto/erro; evite generalidades.
•\tMantenha objetividade: em geral, 1 parágrafo para a correta e 1-2 frases para cada incorreta, detalhando mais apenas quando necessário.
•\tEm questões com cálculo, apresente o raciocínio essencial (fórmulas e passos mínimos) sem usar Latex, declare unidades e critérios de arredondamento quando aplicáveis, evitando derivações longas.
•\tSe algum dado indispensável estiver ausente, explicite a suposição mínima necessária, sem inventar informações não suportadas.

Estrutura sugerida da resposta:
•\tCorreta(s): explique por que está(ão) correta(s).
•\tIncorretas: comente cada alternativa incorreta separadamente (A, B, C, D, E), mantendo as letras originais.
"""
        user_message = f"""
{question_text_with_choices}

Alternativa correta: {correct_choice_letter}
"""
        if image_urls:
            user_content: ResponseInputMessageContentListParam = [
                {"type": "input_text", "text": user_message}
            ]
            user_content.extend(
                [
                    {
                        "type": "input_image",
                        "image_url": image_url,
                        "detail": "high",
                    }
                    for image_url in image_urls
                ]
            )
            return [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_content},
            ]
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]
