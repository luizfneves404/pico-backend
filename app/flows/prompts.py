from typing import ClassVar

from openai import NOT_GIVEN, NotGiven
from openai.types.responses import (
    ResponseInputMessageContentListParam,
    ResponseInputParam,
)
from openai.types.shared_params.reasoning import Reasoning

from app.flows.constants import (
    SYSTEM_MESSAGE_BLOCK_TITLE,
    SYSTEM_MESSAGE_CHECK_MATH_INVOLVEMENT,
    SYSTEM_MESSAGE_GENERATE_TITLE_FROM_TRANSCRIPTIONS,
    SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION,
    SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION_MATH,
    SYSTEM_MESSAGE_QUESTION_GENERATION_THEME,
    SYSTEM_MESSAGE_QUESTION_GENERATION_THEME_MATH,
    SYSTEM_MESSAGE_QUESTION_PERTINENCE_TO_TOPIC,
    QuestionSet,
)
from app.shared.prompts import Prompt, StructuredPrompt

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
    temperature: ClassVar[float | None | NotGiven] = 0.0

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
    temperature: ClassVar[float | None | NotGiven] = 0.0

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


class GenerateQuestionsFromTopic(StructuredPrompt[QuestionSet]):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = 0.0

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
    temperature: ClassVar[float | None | NotGiven] = 0.0

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
    temperature: ClassVar[float | None | NotGiven] = 0.0

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


class GenerateMinorTagsFromQuestion(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = 0.0

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


class GenerateBlockTitle(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = 0.0

    def model(self) -> str:
        return "gpt-5-mini"

    def build_input(self, *, block_text: str) -> ResponseInputParam:
        return [
            {"role": "system", "content": SYSTEM_MESSAGE_BLOCK_TITLE},
            {"role": "user", "content": block_text},
        ]


class GenerateTitleFromTranscriptions(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = 0.0

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


class CheckMathInvolvementFromTitlesOrTopic(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = 0.0

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


class VerifyQuestionPertinenceToTopic(Prompt):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = 0.0

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
    temperature: ClassVar[float | None | NotGiven] = 1.0

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


class GenerateQuestionsFromBlock(StructuredPrompt[QuestionSet]):
    reasoning: ClassVar[Reasoning | None | NotGiven] = {"effort": "medium"}
    temperature: ClassVar[float | None | NotGiven] = 0.0

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
    temperature: ClassVar[float | None | NotGiven] = 0.0

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
