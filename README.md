# Sistema de Gestão de Notas Fiscais Eletrônicas (NF-e)

Este sistema em Python oferece uma solução completa para a importação, controle de estoque e geração de relatórios financeiros a partir de notas fiscais eletrônicas (NF-e). Segundo a especificação do projeto, ele deve ser capaz de **importar NF-e no formato XML** (tanto notas de entrada quanto de saída), **armazenar dados de produtos, quantidades, valores, clientes e fornecedores**, **atualizar o estoque automaticamente** com base nas movimentações das notas, **gerar relatórios financeiros e de estoque detalhados** (incluindo histórico de movimentações e balanços por período) e fornecer uma **interface gráfica (IHM)** para o usuário interagir com essas funcionalidades[\[1\]](file://file_0000000094a0720eb6b293867d685f1e#:~:text=Desenvolver%20um%20sistema%20em%20Python,capaz%20de)[\[2\]](file://file_0000000094a0720eb6b293867d685f1e#:~:text=•%20Atualizar%20automaticamente%20o%20estoque,movimentações%20registradas%20nas%20notas%20fiscais). Em resumo, o objetivo é integrar importação de XML, controle de estoque e análise financeira em um aplicativo prático e de uso intuitivo.

## Requisitos do Sistema

- **Python**: Recomendado Python 3.8 ou superior para execução do sistema[\[3\]](file://file_0000000094a0720eb6b293867d685f1e#:~:text=Linguagem%3A%20Python%203,Bibliotecas%20recomendadas). É importante instalar a versão de Python que inclua suporte ao _tkinter_ (geralmente instalado por padrão), já que a interface gráfica depende dessa biblioteca[\[4\]](file://file_000000008d84720eaaed68014e46ef0e#:~:text=try%3A%20import%20tkinter%20as%20tk,com%20suporte%20à%20biblioteca%20Tk).
- **Bibliotecas obrigatórias** (inclusas no Python): xml.etree.ElementTree (manipulação de XML) e sqlite3 (persistência de dados)[\[5\]](file://file_000000008d84720eaaed68014e46ef0e#:~:text=,recomendações%20de%20bibliotecas%20para%20pequenas). A interface gráfica usa o tkinter (e ttk para estilos)[\[5\]](file://file_000000008d84720eaaed68014e46ef0e#:~:text=,recomendações%20de%20bibliotecas%20para%20pequenas). Além disso, o código utiliza módulos padrão como hashlib, datetime, zipfile e tempfile para funções auxiliares[\[5\]](file://file_000000008d84720eaaed68014e46ef0e#:~:text=,recomendações%20de%20bibliotecas%20para%20pequenas).
- **Bibliotecas opcionais**:
- pandas - para geração de relatórios em CSV/Excel (exportação de dados)[\[6\]](file://file_000000008d84720eaaed68014e46ef0e#:~:text=,opcional%20de%20relatórios%20em%20CSV%2FExcel). Caso o pandas não esteja instalado, essas exportações são simplesmente desativadas de forma transparente.
- matplotlib ou plotly - para geração de gráficos e exportação de relatórios em PDF (requer instalar manualmente)[\[7\]](file://file_0000000094a0720eb6b293867d685f1e#:~:text=•%20matplotlib%20ou%20plotly%20para,gráficos)[\[8\]](file://file_0000000094a0720eb6b293867d685f1e#:~:text=•%20Implementação%20de%20banco%20de,dados%20SQLite%20para%20persistência). O código inclui suporte opcional a exportar tabelas em PDF usando matplotlib, se disponível.
- **Observação:** Caso não utilize exportação gráfica, matplotlib não é obrigatório.

## Instalação

- **Clonar o repositório:** obtenha o código fonte com  

- git clone &lt;URL-do-repositório&gt;
- e entre na pasta do projeto.

- **Instalar dependências:** com o Python instalado, use o pip para instalar as bibliotecas necessárias. Por exemplo, dentro da pasta do projeto rode:  

- pip install pandas matplotlib
- Isso instalará (ou atualizará) o _pandas_ e o _matplotlib_. Se existir um arquivo requirements.txt, basta executar pip install -r requirements.txt. Certifique-se também de que o Python inclui o _tkinter_ (no Linux, instale o pacote python3-tk se necessário).

- **Configurar ambiente:** nada mais especial é requerido - o SQLite3 é parte do Python padrão.

## Como Executar

Para iniciar o aplicativo, execute o arquivo principal pelo terminal:  

python nfe_app.py

Ao rodar o módulo, o sistema abre uma **tela de login** inicial[\[9\]](file://file_000000008d84720eaaed68014e46ef0e#:~:text=Execute%20este%20módulo%20diretamente,código%20para%20facilitar%20a%20compreensão). A janela solicitará **usuário** e **senha**; por padrão há um usuário admin com senha admin já cadastrados. Após um login bem-sucedido, é exibida a **tela principal (menu)** do sistema[\[9\]](file://file_000000008d84720eaaed68014e46ef0e#:~:text=Execute%20este%20módulo%20diretamente,código%20para%20facilitar%20a%20compreensão). Essa tela resume as informações de estoque e finanças iniciais e apresenta botões para acessar as funcionalidades principais: importar notas, consultar estoque, gerar relatórios financeiros e visualizar o histórico de movimentações[\[9\]](file://file_000000008d84720eaaed68014e46ef0e#:~:text=Execute%20este%20módulo%20diretamente,código%20para%20facilitar%20a%20compreensão).

## Funcionalidades Principais

### Importar Notas Fiscais

- Na tela principal, clique em **"Importar Notas"**. Isso abre uma janela onde é possível selecionar **arquivos XML** individuais de NF-e, arquivos compactados ZIP contendo vários XMLs ou até mesmo um **diretório inteiro** com arquivos XML. Você pode adicionar múltiplos arquivos e pastas à lista. Ao iniciar a importação, o sistema processa cada arquivo selecionado: lê o XML, extrai as informações e atualiza o banco de dados SQLite interno (adicionando produtos, clientes/fornecedores e ajustando o estoque conforme entradas/saídas). Ao final, o sistema exibe um resumo indicando quantas notas foram importadas com sucesso, quantas eram duplicadas e se houve erros.

### Consulta de Estoque

- Clique em **"Consultar Estoque"** na tela principal para ver o estoque atual de cada produto. Será exibida uma tabela com as colunas _Código_, _Descrição_ e _Quantidade_ disponível no estoque (por exemplo, cada linha pode aparecer como COD123 | Produto XYZ | 50.00)[\[10\]](file://file_000000008d84720eaaed68014e46ef0e#:~:text=for%20code%2C%20desc%2C%20qty%20in,qty%3A.2f). Se o _pandas_ estiver instalado, aparece também um botão **"Exportar Estoque"**. Clicando nele, você pode salvar a lista de produtos e quantidades em um arquivo CSV ou Excel para análise externa[\[11\]](file://file_000000008d84720eaaed68014e46ef0e#:~:text=if%20HAS_PANDAS%3A%20def%20export_inventory%28%29%20,Quantidade).

### Geração de Relatórios e Exportação

- O sistema permite gerar relatórios financeiros e históricos de movimentações em vários formatos. Em **"Relatório Financeiro"**, informe um período (data inicial e final) e clique em _Calcular_. O aplicativo exibirá os totais de entradas, saídas e o saldo no período selecionado[\[12\]](file://file_000000008d84720eaaed68014e46ef0e#:~:text=f,command%3Dcalculate%29.grid). Há um botão **"Exportar Relatório"** (se o _pandas_ estiver disponível), que salva todas as notas desse período em CSV, Excel ou PDF. Igualmente, em **"Histórico de Movimentações"** você pode filtrar notas por data, tipo (entrada/saída), produto ou entidade (cliente/fornecedor). O resultado aparece em tabela e há opção de exportar também para CSV, Excel ou PDF usando o botão _Exportar Histórico_. A exportação para PDF (que requer instalar o _matplotlib_) gera um arquivo PDF contendo uma tabela com os dados[\[8\]](file://file_0000000094a0720eb6b293867d685f1e#:~:text=•%20Implementação%20de%20banco%20de,dados%20SQLite%20para%20persistência)[\[13\]](file://file_00000000a68071f581e0020ebb6c23a1#:~:text=if%20ext%20%3D%3D%20,Relatório%20salvo%20em). Em todos os casos, após salvar, o sistema exibe mensagem de confirmação com o nome do arquivo gerado.

### Login e Perfis de Usuário

- Ao iniciar o app, é solicitado usuário e senha. O sistema suporta três perfis principais: **administrador**, **operador** e **visualizador**. Conforme a política de acesso, usuários com perfil _administrador_ ou _operador_ podem **importar notas** e **cadastrar novos produtos** (os botões correspondentes ficam habilitados apenas para esses perfis). Já o perfil de _visualizador_ só tem permissão de consulta: pode visualizar o estoque, relatórios financeiros e histórico de movimentações, mas não altera o estoque nem faz importações. Há também um botão **"Log de Acessos"**, que só aparece para o administrador.

## Segurança

- **Tentativas de Login:** O sistema permite até **3 tentativas de login** consecutivas. Se o usuário informar credenciais inválidas três vezes, o acesso fica bloqueado por 1 minuto, tempo em que o botão de login é desativado[\[14\]](file://file_00000000a68071f581e0020ebb6c23a1#:~:text=self.login_button.state%28%5B,Tente%20novamente%20em%201%20minuto). Após esse período, as tentativas são resetadas e o usuário pode tentar novamente.
- **Registro de Acesso:** Todas as tentativas de login (sejam bem-sucedidas ou não) são registradas no banco de dados para fins de auditoria[\[15\]](file://file_00000000a68071f581e0020ebb6c23a1#:~:text=,log_access%28username%2C%20success). Cada entrada no log de acesso inclui o nome de usuário, data/hora e se o login foi bem-sucedido ou não. O perfil de administrador pode visualizar esse log pelo botão "Log de Acessos".
- **Logout:** Em qualquer momento, o usuário logado pode clicar no botão **"Logout"** para sair. Isso encerra a sessão atual e retorna à tela de login sem fechar o programa. Dessa forma, é possível trocar de usuário ou encerrar o acesso de forma segura.