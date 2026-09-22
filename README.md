# AudioClaro em Python

Aplicação Flask pronta para GitHub e Vercel. Ela coleta validações em um banco PostgreSQL, mostra indicadores públicos agregados e protege as respostas individuais e a exportação CSV com uma senha administrativa.

## Recursos

- Landing page responsiva e acessível.
- Entrevista de validação em três etapas.
- API Flask em Python.
- PostgreSQL em produção e SQLite para desenvolvimento local.
- Indicadores agregados sem exposição dos comentários individuais.
- Painel administrativo protegido por `ADMIN_TOKEN`.
- Exportação CSV e exclusão individual de respostas.
- Validação de entrada, honeypot antispam e cabeçalhos básicos de segurança.

## Estrutura

```text
.
├── app.py
├── public/
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── tests/test_app.py
├── .env.example
├── .python-version
└── requirements.txt
```

## Executar localmente

```bash
python -m venv .venv
```

No Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:ADMIN_TOKEN="dev-audioclaro"
python app.py
```

Abra `http://127.0.0.1:5000`. Sem `DATABASE_URL`, a aplicação usa `instance/audioclaro.db` apenas para desenvolvimento.

## Publicar na Vercel

1. Crie um repositório no GitHub e envie todo o conteúdo desta pasta.
2. Na Vercel, selecione **Add New Project** e importe o repositório.
3. Não defina Build Command nem Output Directory. A Vercel detecta o Flask pelo arquivo `app.py`.
4. No Marketplace da Vercel, adicione uma integração PostgreSQL, como Neon.
5. Confirme que a integração criou `DATABASE_URL` nas variáveis do projeto.
6. Em **Settings > Environment Variables**, crie `ADMIN_TOKEN` com uma senha longa e exclusiva.
7. Faça um novo deploy após adicionar as variáveis.
8. Abra `/api/health`; o resultado esperado em produção é `{"status":"ok","storage":"postgres"}`.

## Como usar

Participantes podem responder pelo endereço público. O painel no final da página mostra apenas indicadores agregados. Para acessar respostas individuais e exportar CSV, informe a mesma senha configurada em `ADMIN_TOKEN`.

## Privacidade

- Use códigos como P1 e P2, nunca nomes completos.
- Não solicite áudios, telefones, dados de clientes ou informações confidenciais neste formulário.
- Escolha uma senha administrativa forte.
- Apague dados que não sejam mais necessários após concluir a atividade.
