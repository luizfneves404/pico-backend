STARTING_DUEL_SCORE = 500

ACCESS_TOKEN_EXPIRE_MINUTES = 30

DELETED_USERNAME = "deleted"
DELETED_PHONE_NUMBER = "1121111111"
DELETED_EMAIL = "deleted@sophinity.co"

SENTINEL_USERNAMES = [DELETED_USERNAME]

SOCIAL_SCORE_INCREMENT_BY_REFERRAL = 10

NUM_RANKED_USERS = 10

WELCOME_EMAIL_SUBJECT = "Welcome to Pico!"
WELCOME_EMAIL_MESSAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .container {{
            background-color: #f9f9f9;
            border-radius: 8px;
            padding: 25px;
            border: 1px solid #eaeaea;
        }}
        .header {{
            text-align: center;
            margin-bottom: 20px;
        }}
        .header h1 {{
            color: #2c3e50;
            margin-bottom: 10px;
        }}
        .content {{
            margin-bottom: 25px;
        }}
        .username {{
            font-weight: bold;
            color: #3498db;
        }}
        .footer {{
            text-align: center;
            font-size: 14px;
            color: #7f8c8d;
            margin-top: 30px;
            border-top: 1px solid #eaeaea;
            padding-top: 20px;
        }}
        .contact {{
            margin: 15px 0;
        }}
        .contact a {{
            color: #3498db;
            text-decoration: none;
        }}
        .contact a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Bem-vindo ao Pico!</h1>
        </div>
        <div class="content">
            <p>Parabéns <span class="username">{username}</span>, você criou uma conta no Pico!</p>
            
            <p>Acabamos de confirmar seu cadastro, com o username <span class="username">{username}</span>.</p>
            
            <p>Você é um dos nossos primeiros usuários e estamos muito felizes com sua presença!</p>
            
            <div class="contact">
                <p>Caso você encontre algum problema técnico, ou só queira nos dar alguma sugestão ou saber mais sobre o Pico, fale conosco:</p>
                <p>Instagram: <a href="https://instagram.com/use_pico">@use_pico</a></p>
                <p>E-mail: <a href="mailto:team@usepico.com.br">team@usepico.com.br</a></p>
                <p>Você também pode acessar o nosso site em <a href="https://usepico.com.br">usepico.com.br</a></p>
            </div>
        </div>
        <div class="footer">
            <p>Obrigado pela confiança e boa sorte nos estudos!</p>
        </div>
    </div>
</body>
</html>
"""
