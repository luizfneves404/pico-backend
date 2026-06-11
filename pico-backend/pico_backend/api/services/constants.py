STARTING_DUEL_SCORE = 500

YOU_AND_PICO_CHATROOM_NAME = "Pico"
YOU_AND_PICO_CHATROOM_MESSAGES = [
    {
        "username": "pico",
        "content": "Prazer, sou o Pico e minha missão é te ajudar a tirar boas notas e passar no vestibular! Clicando no meu ícone, à esquerda do teclado, você pode ver minhas funcionalidades. Sempre que quiser que eu responda algo, comece a mensagem com /pico ou simplesmente clique no botão Pico dentro do menu.\n\n"
        "Lembre-se que você também pode criar outros grupos só para você ou com seus amigos!",
    }
]
WELCOME_EMAIL_SUBJECT = "Bem-vindo ao Pico!"
WELCOME_EMAIL_MESSAGE = """Parabéns {username}, você criou uma conta no Pico!

Acabamos de confirmar seu cadastro, com o username
{username}.

Você é um dos nossos primeiros usuários e estamos muito felizes com sua presença!

Caso você encontre algum problema técnico, ou só queira nos dar alguma sugestão ou saber mais sobre o Pico, fale conosco pelo Instagram: @use_pico, ou pelo e-mail team@usepico.com.br

Você também pode acessar o nosso site em https://usepico.com.br

Obrigado pela confiança e boa sorte nos estudos!"""

NUM_RANKED_USERS = 50

SYSTEM_MESSAGE_GENERATE_TRANSCRIPTION_FROM_IMAGE = """Você recebeu a tarefa de transcrever o conteúdo acadêmico presente em uma imagem de um caderno ou material escolar.

Regras importantes:
1. Transcreva TODO o conteúdo acadêmico de forma clara e completa
2. Ignore informações pessoais, rabiscos ou anotações não relacionadas
3. Não mencione a imagem ou faça referência a ela
4. Não adicione comentários ou observações próprias

Forneça apenas o conteúdo acadêmico transcrito."""

SYSTEM_MESSAGE_DELATEXIFY = """Você recebeu a tarefa de transformar um texto em LaTeX.
Você deve substituir todas as expressões LaTeX por uma versão que pode ser renderizada como texto comum, usando símbolos e palavras.
Para operações matemáticas, priorize símbolos simples no lugar de palavras ao indicar operações, como em: "5 . 5" em vez de "5 vezes 5".
Se não houver LaTeX na mensagem, você deve devolver apenas a mensagem original INALTERADA.
"""

SYSTEM_MESSAGE_TRANSCRIBE_PDF = """Sua tarefa é transcrever com total fidelidade todo o conteúdo acadêmico do PDF fornecido, preservando a estrutura, a formatação e o texto original, sem interpretações, resumos ou comentários adicionais. Responda apenas com a transcrição fiel e completa do conteúdo, iniciando diretamente pelo texto do documento, sem introduções ou frases como 'Claro!' ou 'Aqui está a transcrição:'
"""
