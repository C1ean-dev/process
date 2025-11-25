# Sistema de Processamento de Documentos

Este é um sistema web desenvolvido com Flask para upload, processamento (OCR) e gerenciamento de documentos. Ele utiliza CloudAMQP para fila de mensagens e workers multiprocessing para processar arquivos de forma assíncrona, com sistema de reprocessamento para tarefas que falham.

## Funcionalidades

*   **Upload de Arquivos**: Permite o upload de arquivos de imagem (PNG, JPG, JPEG, GIF) e PDF.
*   **Processamento Assíncrono**: Utiliza workers para processar arquivos em segundo plano, evitando travamento da interface.
*   **OCR (Optical Character Recognition)**: Extrai texto de imagens e PDFs usando Tesseract.
*   **Compressão de PDF**: Otimiza o tamanho de arquivos PDF.
*   **Extração de Texto de PDF**: Extrai texto de PDFs para processamento.
*   **Gerenciamento de Status**: Acompanha o status de cada arquivo (pendente, processando, completo, falhou, reprocessando).
*   **Reprocessamento Automático**: Tenta reprocessar tarefas que falham até 3 vezes.
*   **Monitoramento de Pastas**: Um monitor de pasta verifica periodicamente a pasta de arquivos pendentes para garantir que todos os arquivos sejam processados, mesmo que não tenham sido adicionados via upload ou se o aplicativo foi reiniciado.
*   **Organização de Pastas**: Os arquivos são movidos entre pastas de acordo com seu status de processamento.

### Pré-requisitos

*   Python 3.x
*   Tesseract OCR: Instale o Tesseract OCR em seu sistema.
    *   **Windows**: Baixe e instale a versão mais recente em [https://tesseract-ocr.github.io/tessdoc/Downloads.html](https://tesseract-ocr.github.io/tessdoc/Downloads.html). Certifique-se de adicionar o Tesseract ao seu PATH ou configurar `pytesseract.pytesseract.tesseract_cmd` em `app/workers/tasks.py`.
    *   **Linux (Ubuntu/Debian)**: `sudo apt-get install tesseract-ocr`
    *   **macOS**: `brew install tesseract`

### Passos

1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/C1ean-dev/process
    cd process
    ```

2.  **Crie e ative um ambiente virtual:**
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configuração do Banco de Dados (SQLite padrão)**:
    O aplicativo usa SQLite por padrão (`site.db`). Se você modificou o modelo `File` (adicionando a coluna `retries`), você precisará atualizar o banco de dados.

    *   **Opção 1 (Recomendado para Desenvolvimento)**: Exclua o arquivo `site.db` (localizado em `instance/site.db` dentro do diretório do projeto) e o aplicativo o recriará automaticamente na próxima execução.
    *   **Opção 2 (Para Produção)**: Use o comando `python -m app recreate_db` para recriar o banco de dados (⚠️ **ATENÇÃO**: Este comando deleta todos os dados existentes).

5.  **Defina variáveis de ambiente:**
    Crie um arquivo `.env` na raiz do projeto com:
    ```
    SECRET_KEY='sua_chave_secreta_aqui'
    DATABASE_URL='sqlite:///site.db' # Ou sua URL de banco de dados

    # Configurações do Tesseract e Poppler (EX para Windows, ajuste conforme seu SO)
    TESSERACT_CMD='C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
    POPPLER_PATH='C:\\poppler\\Library\\bin'

    # Feature Flags
    ENABLE_OCR='True'
    R2_FEATURE_FLAG='True'

    # Cloudflare R2 (S3-compatible) Configuration
    CLOUDFLARE_ACCOUNT_ID='seu_account_id_r2'
    CLOUDFLARE_R2_ACCESS_KEY_ID='sua_access_key_id_r2'
    CLOUDFLARE_R2_SECRET_ACCESS_KEY='sua_secret_access_key_r2'
    CLOUDFLARE_R2_BUCKET_NAME='seu_bucket_name_r2'
    CLOUDFLARE_R2_ENDPOINT_URL='seu_endpoint_url_r2'

    # CloudAMQP Configuration
    CLOUDAMQP_URL='amqps://user:password@host/vhost' # URL fornecida pelo CloudAMQP
    NUM_WORKERS=4 # Número de workers multiprocessing
    ```

## Como Executar

1.  **Ative seu ambiente virtual** (se ainda não estiver ativo).
2.  **Execute o aplicativo Flask:**
    ```bash
    python -m app
    ```
    O aplicativo será executado em `http://127.0.0.1:5000/` (ou outra porta, se configurado).

## Uso

1.  Acesse a URL do aplicativo no seu navegador.
2.  Se for a primeira vez, você será redirecionado para a página de configuração de administrador. Crie um usuário administrador.
3.  Faça login com suas credenciais.
4.  Navegue até a página de upload para enviar seus documentos.
5.  Acompanhe o status dos seus arquivos na página de dados.
6.  Acompanhe o status dos seus arquivos na página de dados.

## Contribuição

Sinta-se à vontade para contribuir com este projeto.

## Licença

## Tecnologias Utilizadas

*   **Flask**: Microframework web para Python.
*   **SQLAlchemy**: ORM para interação com o banco de dados.
*   **CloudAMQP**: Serviço de fila de mensagens baseado em RabbitMQ para processamento assíncrono.
*   **Pika**: Biblioteca Python para interação com RabbitMQ (usada com CloudAMQP).
*   **Tesseract OCR**: Motor de OCR para extração de texto.
*   **Pillow**: Biblioteca de processamento de imagens.
*   **PyPDF2 / pypdf**: Biblioteca para manipulação de PDFs.
*   **pdf2image**: Conversão de PDFs para imagens para OCR.
*   **Cloudflare R2**: Armazenamento de objetos compatível com S3 para armazenamento de arquivos.
*   **Boto3**: Cliente para AWS S3 (usado com Cloudflare R2).
*   **Flask-Login**: Gerenciamento de autenticação de usuários.
*   **Flask-WTF**: Formulários web seguros.
*   **Prometheus Client**: Para métricas e monitoramento.
*   **Plotly & Matplotlib**: Para visualização de dados (se usado).

## Licença

Este projeto está licenciado sob a Licença MIT.
