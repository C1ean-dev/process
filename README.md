# Sistema de Processamento de Documentos

Este é um sistema web desenvolvido com Flask para upload, processamento (OCR) e gerenciamento de documentos. Ele utiliza workers em segundo plano para processar arquivos de forma assíncrona e inclui um sistema de reprocessamento para tarefas que falham.

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

## Estrutura de Pastas

O projeto utiliza as seguintes pastas para organizar os arquivos:

*   `uploads/`: Onde os arquivos são inicialmente salvos após o upload pelo usuário.
*   `aguardando_processo/`: (PENDING_FOLDER) Onde os arquivos aguardam para serem processados pelos workers. Arquivos que falham e serão reprocessados também retornam para esta pasta.
*   `processando/`: (PROCESSING_FOLDER) Onde os arquivos ficam enquanto estão sendo ativamente processados por um worker.
*   `completos/`: (COMPLETED_FOLDER) Onde os arquivos são movidos após serem processados com sucesso.
*   `falhas/`: (FAILED_FOLDER) Onde os arquivos são movidos se falharem no processamento após todas as tentativas.

## Instalação

### Pré-requisitos

*   Python 3.x
*   Tesseract OCR: Instale o Tesseract OCR em seu sistema.
    *   **Windows**: Baixe e instale a versão mais recente em [https://tesseract-ocr.github.io/tessdoc/Downloads.html](https://tesseract-ocr.github.io/tessdoc/Downloads.html). Certifique-se de adicionar o Tesseract ao seu PATH ou configurar `pytesseract.pytesseract.tesseract_cmd` em `app/workers/tasks.py`.
    *   **Linux (Ubuntu/Debian)**: `sudo apt-get install tesseract-ocr`
    *   **macOS**: `brew install tesseract`

### Passos

1.  **Clone o repositório:**
    ```bash
    git clone [URL_DO_SEU_REPOSITORIO]
    cd [NOME_DO_SEU_REPOSITORIO]
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
    *   **Opção 2 (Para Produção com Flask-Migrate)**: Se você estiver usando Flask-Migrate, execute os comandos de migração:
        ```bash
        flask db migrate -m "Add retries column to File model"
        flask db upgrade
        ```

5.  **Defina variáveis de ambiente:**
    Crie um arquivo `.env` na raiz do projeto com:
    ```
    SECRET_KEY='sua_chave_secreta_aqui'
    DATABASE_URL='sqlite:///site.db' # Ou sua URL de banco de dados

    # Configurações do Tesseract e Poppler (EX para Windows, ajuste conforme seu SO)
    TESSERACT_CMD='C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
    POPPLER_PATH='C:\\poppler\\Library\\bin'
    GHOSTSCRIPT_EXEC='C:\\Program Files\\gs\\gs10.05.1\\bin\\gswin64c.exe'

    # Feature Flags
    ENABLE_PDF_COMPRESSION='True' (Beta no momento ela está aumentando o tamanho do arquivo ainda não sei o pq)
    ENABLE_OCR='True'

    # Cloudflare R2 (S3-compatible) Configuration
    CLOUDFLARE_ACCOUNT_ID='seu_account_id_r2'
    CLOUDFLARE_R2_ACCESS_KEY_ID='sua_access_key_id_r2'
    CLOUDFLARE_R2_SECRET_ACCESS_KEY='sua_secret_access_key_r2'
    CLOUDFLARE_R2_BUCKET_NAME='seu_bucket_name_r2'
    CLOUDFLARE_R2_ENDPOINT_URL='seu_endpoint_url_r2'
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

## Contribuição

Sinta-se à vontade para contribuir com este projeto.

## Licença

## Tecnologias Utilizadas

*   **Flask**: Microframework web para Python.
*   **SQLAlchemy**: ORM para interação com o banco de dados.
*   **Celery**: Sistema de fila de tarefas distribuídas para processamento assíncrono.
*   **Redis**: Broker de mensagens para Celery e cache.
*   **Tesseract OCR**: Motor de OCR para extração de texto.
*   **Pillow**: Biblioteca de processamento de imagens.
*   **PyPDF2**: Biblioteca para manipulação de PDFs.
*   **Cloudflare R2**: Armazenamento de objetos compatível com S3 para armazenamento de arquivos.

## Licença

Este projeto está licenciado sob a Licença MIT.
