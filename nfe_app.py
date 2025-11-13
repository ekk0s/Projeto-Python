"""
Sistema de Gestão Financeira e de Estoque com NF‑e
==================================================

Este módulo implementa um pequeno sistema em Python capaz de importar
notas fiscais eletrônicas (NF‑e) em formato XML, organizar as
informações dos produtos, clientes e fornecedores em um banco de dados
SQLite, atualizar automaticamente o estoque e gerar relatórios. Uma
interface gráfica simples foi construída com Tkinter para facilitar a
interação com o usuário. O projeto segue os requisitos descritos no
documento de especificação, incluindo a importação de notas de
entrada e saída, armazenamento de produtos, atualização de estoque,
relatórios financeiros e de estoque e uma IHM para operação do
sistema【122648825277977†L34-L45】【122648825277977†L100-L121】.

Bibliotecas externas utilizadas
-------------------------------

- ``xml.etree.ElementTree``: para leitura e navegação nos arquivos
  XML de NF‑e. O uso da biblioteca é sugerido nos materiais do
  projeto【122648825277977†L134-L143】.
- ``sqlite3``: armazenamento persistente das informações em um
  banco de dados leve e portável, conforme objetivo de implementar
  persistência opcional【122648825277977†L83-L96】.
- ``tkinter`` e ``ttk``: construção da interface gráfica (IHM) de
  acordo com as recomendações de bibliotecas para pequenas
  aplicações【478165176142609†L60-L72】.
- ``hashlib``: hashing simples de senhas de usuário.
- ``datetime``: manipulação de datas e períodos.
- ``zipfile`` e ``tempfile``: suporte à importação de arquivos
  compactados.
- ``pandas``: geração opcional de relatórios em CSV/Excel.

Como usar
---------

Execute este módulo diretamente. Será exibida uma janela de login
(usuário: ``admin``, senha: ``admin`` por padrão). Após logar, a
tela principal permite importar notas, consultar estoque, gerar
relatórios financeiros e visualizar o histórico de movimentações. As
funções estão comentadas no código para facilitar a compreensão.

"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Callable
import xml.etree.ElementTree as ET

# Tente importar pandas; caso não esteja disponível, as exportações
# opcionais serão desativadas graciosamente.
try:
    import pandas as pd  # type: ignore
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# Importação condicional de matplotlib para exportação PDF. Não exigimos
# matplotlib para o funcionamento básico, mas ele é necessário para
# gerar gráficos e relatórios em PDF. A importação é feita sob demanda
# nas funções que utilizam a biblioteca.

def export_dataframe_to_pdf(df: 'pd.DataFrame', file_path: str, title: str = "Relatório") -> None:
    """Gera um PDF simples contendo uma tabela com os dados de um DataFrame.

    Esta função utiliza matplotlib para desenhar uma tabela contendo todas as
    linhas e colunas do DataFrame e salva o resultado no caminho
    especificado. Se a biblioteca matplotlib não estiver disponível, a
    função lançará uma exceção.

    :param df: DataFrame a exportar
    :param file_path: Caminho completo do arquivo PDF de saída
    :param title: Título a ser exibido no topo do PDF
    """
    try:
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except ImportError:
        raise RuntimeError("Matplotlib não está disponível para exportação em PDF.")
    # Cria figura ajustando o tamanho de acordo com o número de linhas
    n_rows, n_cols = df.shape
    # Define tamanho base: largura fixa, altura proporcional ao número de linhas
    fig_width = max(8.0, n_cols * 1.5)
    fig_height = max(3.0, 0.4 * n_rows + 1.5)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.set_axis_off()
    # Adiciona título
    ax.set_title(title, fontsize=12, pad=10)
    # Constrói tabela de dados
    table = ax.table(
        cellText=df.values.tolist(),
        colLabels=df.columns.tolist(),
        cellLoc='center',
        loc='center',
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.2)
    # Ajusta layout para caber a tabela
    plt.tight_layout()
    # Salva em PDF
    with PdfPages(file_path) as pdf:
        pdf.savefig(fig, bbox_inches='tight')
    plt.close(fig)

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from tkinter import ttk
except ImportError:
    raise RuntimeError(
        "Tkinter não está disponível. Certifique‑se de que o Python foi instalado "
        "com suporte à biblioteca Tk."
    )

###############################################################################
# Configurações globais
###############################################################################

# Namespace da NF‑e para facilitar a busca no XML
NS = {"ns": "http://www.portalfiscal.inf.br/nfe"}


def hash_password(password: str) -> str:
    """Gera um hash SHA‑256 simples para armazenar senhas."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


@dataclass
class ParsedItem:
    """Representa um item de nota fiscal extraído do XML."""

    product_code: str
    description: str
    quantity: float
    unit_price: float
    total: float


@dataclass
class ParsedNote:
    """Representa as informações gerais de uma nota fiscal."""

    key: str
    date: datetime
    type: str  # "entrada" ou "saida"
    entity_name: str
    entity_cnpj: str
    total: float
    items: List[ParsedItem]


def parse_xml_file(file_path: str) -> ParsedNote:
    """Lê um arquivo XML de NF‑e e devolve um objeto ParsedNote.

    A função tenta extrair as principais informações de cabeçalho e os
    itens. Caso falte algum campo esperado, a exceção será propagada.
    """
    tree = ET.parse(file_path)
    root = tree.getroot()

    # Localiza o elemento infNFe. Alguns arquivos podem ter nfeProc como
    # raiz; por isso usamos .// para procurar em profundidade.
    inf = root.find('.//ns:infNFe', NS)
    if inf is None:
        raise ValueError(f"Arquivo {file_path} não possui infNFe")

    # Chave da nota (Id sem prefixo 'NFe' se existir)
    key_attr = inf.get("Id", "").replace("NFe", "")

    # Data de emissão
    ide = inf.find('ns:ide', NS)
    if ide is None:
        raise ValueError(f"Arquivo {file_path} sem elemento ide")
    # Tenta extrair a data/hora de emissão. Conforme o documento de projeto,
    # algumas notas utilizam o campo dhEmi (data e hora) e outras usam dEmi
    # (apenas data). Procuramos dhEmi inicialmente; se estiver vazio ou
    # inexistente, buscamos dEmi como alternativa.
    dh_emi_text = ide.findtext('ns:dhEmi', default="", namespaces=NS)
    if not dh_emi_text:
        dh_emi_text = ide.findtext('ns:dEmi', default="", namespaces=NS)
    # Converte para datetime; remove o fuso horário se presente. Se a
    # conversão falhar, usa a data atual como fallback.
    date_obj = None
    if dh_emi_text:
        try:
            # ISO 8601: a data pode conter um offset (ex: 2025-10-31T13:11:06-03:00)
            # ou apenas a data (ex: 2025-10-31). O fromisoformat trata ambos.
            date_obj = datetime.fromisoformat(dh_emi_text.replace("Z", "+00:00"))
        except Exception:
            date_obj = None
    if not date_obj:
        # Se não for possível interpretar a data, utiliza o momento atual
        date_obj = datetime.now()

    # Tipo de nota: 0=entrada, 1=saída
    tpNF_text = ide.findtext('ns:tpNF', default="1", namespaces=NS)
    note_type = "entrada" if tpNF_text.strip() == "0" else "saida"

    # Entidades: emitente e destinatário
    emit = inf.find('ns:emit', NS)
    dest = inf.find('ns:dest', NS)
    if emit is None or dest is None:
        raise ValueError(f"Arquivo {file_path} sem emitente ou destinatário")

    # Para notas de entrada, o emitente é o fornecedor; para saída, o
    # destinatário é o cliente. Caso contrário, assumimos o oposto.
    if note_type == "entrada":
        entity_cnpj = emit.findtext('ns:CNPJ', default="", namespaces=NS) or emit.findtext('ns:CPF', default="", namespaces=NS)
        entity_name = emit.findtext('ns:xNome', default="", namespaces=NS)
    else:
        entity_cnpj = dest.findtext('ns:CNPJ', default="", namespaces=NS) or dest.findtext('ns:CPF', default="", namespaces=NS)
        entity_name = dest.findtext('ns:xNome', default="", namespaces=NS)

    # Valor total da nota
    total_element = inf.find('ns:total/ns:ICMSTot', NS)
    if total_element is not None:
        total_value = float(total_element.findtext('ns:vNF', default="0", namespaces=NS))
    else:
        total_value = 0.0

    # Itens (det)
    items: List[ParsedItem] = []
    for det in inf.findall('ns:det', NS):
        prod = det.find('ns:prod', NS)
        if prod is None:
            continue
        code = prod.findtext('ns:cProd', default="", namespaces=NS)
        desc = prod.findtext('ns:xProd', default="", namespaces=NS)
        qty = float(prod.findtext('ns:qCom', default="0", namespaces=NS))
        unit_price = float(prod.findtext('ns:vUnCom', default="0", namespaces=NS))
        total = float(prod.findtext('ns:vProd', default="0", namespaces=NS))
        items.append(ParsedItem(code, desc, qty, unit_price, total))

    return ParsedNote(
        key=key_attr,
        date=date_obj,
        type=note_type,
        entity_name=entity_name,
        entity_cnpj=entity_cnpj,
        total=total_value,
        items=items,
    )


class Database:
    """Classe responsável pela persistência em banco de dados SQLite."""

    def __init__(self, db_path: str = "nfe_system.db") -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.create_tables()

    def create_tables(self) -> None:
        """Cria todas as tabelas necessárias caso não existam."""
        c = self.conn.cursor()
        # Tabela de usuários
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'admin'
            )
            """
        )
        # Entidades (clientes/fornecedores)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cnpj_cpf TEXT NOT NULL,
                type TEXT NOT NULL
            )
            """
        )
        # Produtos
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY,
                description TEXT NOT NULL
            )
            """
        )
        # Notas
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                entity_id INTEGER,
                total REAL,
                FOREIGN KEY (entity_id) REFERENCES entities(id)
            )
            """
        )
        # Itens de notas
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS note_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id INTEGER NOT NULL,
                product_code TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit_price REAL NOT NULL,
                total REAL NOT NULL,
                FOREIGN KEY (note_id) REFERENCES notes(id),
                FOREIGN KEY (product_code) REFERENCES products(code)
            )
            """
        )
        # Estoque: quantidade disponível por produto
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                product_code TEXT PRIMARY KEY,
                stock_quantity REAL NOT NULL,
                FOREIGN KEY (product_code) REFERENCES products(code)
            )
            """
        )
        # Logs de acesso (para controle de login)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                success INTEGER NOT NULL
            )
            """
        )
        self.conn.commit()

    def add_user(self, username: str, password: str, role: str = "admin") -> None:
        """Adiciona um usuário. Caso já exista, não faz nada."""
        c = self.conn.cursor()
        c.execute("SELECT username FROM users WHERE username = ?", (username,))
        if c.fetchone():
            return
        c.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, hash_password(password), role),
        )
        self.conn.commit()

    def verify_user(self, username: str, password: str) -> bool:
        """Verifica se o usuário e senha informados são válidos."""
        c = self.conn.cursor()
        c.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        )
        row = c.fetchone()
        if row and row[0] == hash_password(password):
            return True
        return False

    def get_user_role(self, username: str) -> Optional[str]:
        """Retorna o papel de um usuário (admin, operador ou visualizador).

        Se o usuário não existir, retorna None.
        """
        c = self.conn.cursor()
        c.execute("SELECT role FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        return row[0] if row else None

    def log_access(self, username: str, success: bool) -> None:
        """Registra tentativas de login para auditoria."""
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO access_log (username, timestamp, success) VALUES (?, ?, ?)",
            (username, datetime.now().isoformat(), 1 if success else 0),
        )
        self.conn.commit()

    def get_access_logs(self, limit: Optional[int] = None) -> List[Tuple[str, str, int]]:
        """Retorna uma lista de logs de acesso ordenados por data decrescente.

        :param limit: Se fornecido, limita o número de registros retornados
        :return: lista de tuplas (username, timestamp, success)
        """
        c = self.conn.cursor()
        query = "SELECT username, timestamp, success FROM access_log ORDER BY timestamp DESC"
        if limit:
            query += " LIMIT ?"
            c.execute(query, (limit,))
        else:
            c.execute(query)
        return c.fetchall()

    def get_or_create_entity(self, name: str, cnpj_cpf: str, entity_type: str) -> int:
        """Retorna o ID de uma entidade, criando-a se necessário."""
        c = self.conn.cursor()
        c.execute(
            "SELECT id FROM entities WHERE cnpj_cpf = ? AND type = ?",
            (cnpj_cpf, entity_type),
        )
        row = c.fetchone()
        if row:
            return row[0]
        c.execute(
            "INSERT INTO entities (name, cnpj_cpf, type) VALUES (?, ?, ?)",
            (name, cnpj_cpf, entity_type),
        )
        self.conn.commit()
        return c.lastrowid

    def add_or_update_product(self, code: str, description: str) -> None:
        """Garante que o produto exista na tabela products."""
        c = self.conn.cursor()
        c.execute("SELECT code FROM products WHERE code = ?", (code,))
        if c.fetchone():
            return
        c.execute(
            "INSERT INTO products (code, description) VALUES (?, ?)",
            (code, description),
        )
        self.conn.commit()

    def insert_note(self, parsed: ParsedNote) -> bool:
        """Insere uma nota fiscal e seus itens no banco de dados.

        O estoque é atualizado automaticamente de acordo com o tipo da nota
        (entrada aumenta, saída diminui). Caso a nota já exista (chave
        duplicada), ela não será inserida novamente.

        :param parsed: ParsedNote a inserir
        :return: True se a nota foi inserida, False se já existia
        """
        c = self.conn.cursor()
        c.execute("SELECT id FROM notes WHERE key = ?", (parsed.key,))
        if c.fetchone():
            # Nota já existente
            return False

        # Descobre o tipo de entidade baseado no tipo de nota
        entity_type = "fornecedor" if parsed.type == "entrada" else "cliente"
        entity_id = self.get_or_create_entity(parsed.entity_name, parsed.entity_cnpj, entity_type)

        # Insere nota
        c.execute(
            "INSERT INTO notes (key, date, type, entity_id, total) VALUES (?, ?, ?, ?, ?)",
            (
                parsed.key,
                parsed.date.isoformat(),
                parsed.type,
                entity_id,
                parsed.total,
            ),
        )
        note_id = c.lastrowid

        # Insere itens e atualiza estoque
        for item in parsed.items:
            self.add_or_update_product(item.product_code, item.description)
            # Inserir item
            c.execute(
                "INSERT INTO note_items (note_id, product_code, quantity, unit_price, total) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    note_id,
                    item.product_code,
                    item.quantity,
                    item.unit_price,
                    item.total,
                ),
            )
            # Atualiza estoque
            self.update_inventory(item.product_code, item.quantity, parsed.type)
        self.conn.commit()
        return True

    def update_inventory(self, product_code: str, quantity: float, note_type: str) -> None:
        """Atualiza o estoque conforme o tipo de nota (entrada ou saída)."""
        c = self.conn.cursor()
        # Recupera quantidade atual
        c.execute(
            "SELECT stock_quantity FROM inventory WHERE product_code = ?",
            (product_code,),
        )
        row = c.fetchone()
        current_qty = row[0] if row else 0.0
        if note_type == "entrada":
            new_qty = current_qty + quantity
        else:
            new_qty = current_qty - quantity
        if row:
            c.execute(
                "UPDATE inventory SET stock_quantity = ? WHERE product_code = ?",
                (new_qty, product_code),
            )
        else:
            c.execute(
                "INSERT INTO inventory (product_code, stock_quantity) VALUES (?, ?)",
                (product_code, new_qty),
            )
        # Não faz commit aqui para permitir transações agrupadas; commit é feito no final da importação

    def query_inventory(self) -> List[Tuple[str, str, float]]:
        """Retorna o estoque atual (código, descrição, quantidade)."""
        c = self.conn.cursor()
        c.execute(
            "SELECT p.code, p.description, i.stock_quantity FROM products p "
            "JOIN inventory i ON p.code = i.product_code ORDER BY p.description"
        )
        return c.fetchall()

    def query_financial_summary(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Calcula totais de notas de entrada, saída e saldo líquido.

        Se datas forem informadas, filtra por período [start_date, end_date].
        """
        c = self.conn.cursor()
        params: List[str] = []
        date_filter = ""
        if start_date and end_date:
            date_filter = "WHERE date BETWEEN ? AND ?"
            params.extend([start_date.isoformat(), end_date.isoformat()])
        elif start_date:
            date_filter = "WHERE date >= ?"
            params.append(start_date.isoformat())
        elif end_date:
            date_filter = "WHERE date <= ?"
            params.append(end_date.isoformat())
        c.execute(
            f"SELECT type, SUM(total) FROM notes {date_filter} GROUP BY type",
            params,
        )
        totals = {"entrada": 0.0, "saida": 0.0}
        for t_type, total in c.fetchall():
            totals[t_type] = total or 0.0
        totals["saldo"] = totals.get("entrada", 0.0) - totals.get("saida", 0.0)
        return totals

    def query_notes(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        note_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retorna uma lista de notas com dados básicos e o total.

        Permite filtrar por período e tipo (entrada/saida).
        """
        c = self.conn.cursor()
        filters = []
        params: List[str] = []
        if start_date:
            filters.append("date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            filters.append("date <= ?")
            params.append(end_date.isoformat())
        if note_type in ("entrada", "saida"):
            filters.append("type = ?")
            params.append(note_type)
        where_clause = ""
        if filters:
            where_clause = "WHERE " + " AND ".join(filters)
        c.execute(
            """
            SELECT n.id, n.key, n.date, n.type, e.name, n.total
            FROM notes n
            LEFT JOIN entities e ON n.entity_id = e.id
            {where}
            ORDER BY n.date
            """.format(where=where_clause),
            params,
        )
        rows = c.fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "key": row[1],
                    "date": row[2],
                    "type": row[3],
                    "entity": row[4],
                    "total": row[5],
                }
            )
        return result

    def get_note_items(self, note_id: int) -> List[Dict[str, Any]]:
        """Retorna todos os itens de uma nota pelo ID."""
        c = self.conn.cursor()
        c.execute(
            """
            SELECT p.description, ni.product_code, ni.quantity, ni.unit_price, ni.total
            FROM note_items ni
            JOIN products p ON p.code = ni.product_code
            WHERE ni.note_id = ?
            """,
            (note_id,),
        )
        rows = c.fetchall()
        return [
            {
                "description": desc,
                "code": code,
                "quantity": qty,
                "unit_price": price,
                "total": total,
            }
            for desc, code, qty, price, total in rows
        ]

    def get_all_products(self) -> List[Tuple[str, str]]:
        """Retorna todos os produtos cadastrados (código e descrição)."""
        c = self.conn.cursor()
        c.execute("SELECT code, description FROM products ORDER BY description")
        return c.fetchall()

    def get_all_entities(self) -> List[Tuple[int, str]]:
        """Retorna todos os nomes de entidades (clientes/fornecedores)."""
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM entities ORDER BY name")
        return c.fetchall()

    def query_notes_filtered(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        note_type: Optional[str] = None,
        product_code: Optional[str] = None,
        entity_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retorna notas filtradas por período, tipo, produto e entidade.

        Esta função permite realizar consultas mais refinadas do que
        query_notes, incluindo filtros por código de produto (presente
        em note_items) e por entidade (cliente ou fornecedor). Quando
        nenhum filtro adicional é fornecido, o comportamento é
        equivalente a query_notes.

        :param start_date: início do período (inclusive)
        :param end_date: fim do período (inclusive)
        :param note_type: "entrada" ou "saida"
        :param product_code: código do produto para filtrar
        :param entity_id: id da entidade para filtrar
        :return: lista de notas com dados básicos
        """
        c = self.conn.cursor()
        conditions = []
        params: List[str] = []
        join_clause = ""
        if start_date:
            conditions.append("n.date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("n.date <= ?")
            params.append(end_date.isoformat())
        if note_type in ("entrada", "saida"):
            conditions.append("n.type = ?")
            params.append(note_type)
        if entity_id:
            conditions.append("n.entity_id = ?")
            params.append(str(entity_id))
        # Se filtro de produto, adiciona join com note_items
        if product_code:
            join_clause = "JOIN note_items ni ON ni.note_id = n.id AND ni.product_code = ?"
            params.append(product_code)
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        query = f"""
            SELECT DISTINCT n.id, n.key, n.date, n.type, e.name, n.total
            FROM notes n
            LEFT JOIN entities e ON n.entity_id = e.id
            {join_clause}
            {where_clause}
            ORDER BY n.date
        """
        c.execute(query, params)
        rows = c.fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "key": row[1],
                    "date": row[2],
                    "type": row[3],
                    "entity": row[4],
                    "total": row[5],
                }
            )
        return result


class NFeAppGUI:
    """Classe principal da interface gráfica do sistema."""

    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self.master.title("Sistema de Gestão Financeira e de Estoque")
        self.db = Database()
        # Cria usuário admin padrão caso não exista
        self.db.add_user("admin", "admin")
        # Mostra tela de login
        self.show_login_window()
        # Atributos para rastrear usuário atual e papel
        self.current_user: Optional[str] = None
        self.current_role: Optional[str] = None

    def show_login_window(self) -> None:
        """Exibe a tela de login."""
        self.clear_window()
        frame = ttk.Frame(self.master, padding=20)
        frame.pack(expand=True)
        ttk.Label(frame, text="Usuário:").grid(row=0, column=0, sticky="e")
        self.username_entry = ttk.Entry(frame)
        self.username_entry.grid(row=0, column=1, pady=5)
        self.username_entry.focus_set()  # Foco inicial no usuário
        ttk.Label(frame, text="Senha:").grid(row=1, column=0, sticky="e")
        self.password_entry = ttk.Entry(frame, show="*")
        self.password_entry.grid(row=1, column=1, pady=5)
        # Inicializa contador de tentativas restantes
        self.remaining_attempts = 3
        # Checkbutton para mostrar/ocultar senha
        show_var = tk.BooleanVar(value=False)
        def toggle_password() -> None:
            if show_var.get():
                self.password_entry.config(show="")
            else:
                self.password_entry.config(show="*")
        chk = ttk.Checkbutton(frame, text="Mostrar senha", variable=show_var, command=toggle_password)
        chk.grid(row=2, column=1, sticky="w")
        # Botão de login
        self.login_button = ttk.Button(frame, text="Entrar", command=self.handle_login)
        self.login_button.grid(row=3, column=0, columnspan=2, pady=10)
        # Permite login com Enter
        self.master.bind("<Return>", lambda event: self.handle_login())

    def handle_login(self) -> None:
        """Processa as credenciais inseridas pelo usuário."""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        success = self.db.verify_user(username, password)
        # Registra tentativa de acesso
        self.db.log_access(username, success)
        if success:
            # Reseta contador de tentativas
            self.remaining_attempts = 3
            # Armazena usuário e papel para controle de acesso
            self.current_user = username
            self.current_role = self.db.get_user_role(username)
            self.show_main_menu()
        else:
            # Falha de login
            self.remaining_attempts -= 1
            if self.remaining_attempts > 0:
                messagebox.showerror(
                    "Erro de login",
                    f"Usuário ou senha inválidos. Tentativas restantes: {self.remaining_attempts}.",
                )
            else:
                # Desativa botão e agenda reativação após 60 segundos
                self.login_button.state(["disabled"])
                messagebox.showerror(
                    "Acesso bloqueado",
                    "Número máximo de tentativas alcançado. Tente novamente em 1 minuto.",
                )
                def reenable() -> None:
                    self.remaining_attempts = 3
                    self.login_button.state(["!disabled"])
                # Reativa após 60 segundos (60000 ms)
                self.master.after(60000, reenable)

    def show_main_menu(self) -> None:
        """Exibe o menu principal após login.

        Esta tela fornece um resumo de estoque e finanças e apresenta as opções
        disponíveis ao usuário, de acordo com seu papel (administrador,
        operador ou visualizador). O botão "Logout" retorna à tela de login.
        """
        self.clear_window()
        frame = ttk.Frame(self.master, padding=20)
        frame.pack(expand=True, fill="both")
        # Saudação com o nome do usuário
        user_display = self.current_user or "usuário"
        ttk.Label(
            frame,
            text=f"Bem‑vindo, {user_display}!",
            font=("Arial", 14, "bold"),
        ).pack(pady=5)
        # Resumo de estoque e finanças
        summary_frame = ttk.LabelFrame(frame, text="Resumo do Estoque e Finanças", padding=10)
        summary_frame.pack(fill="x", pady=10)
        # Calcula indicadores
        inventory_data = self.db.query_inventory()
        num_products = len(inventory_data)
        total_stock = sum(qty for _, _, qty in inventory_data)
        negative_count = sum(1 for _, _, qty in inventory_data if qty < 0)
        totals = self.db.query_financial_summary()
        # Cria rótulos
        ttk.Label(summary_frame, text=f"Produtos cadastrados: {num_products}").grid(row=0, column=0, sticky="w")
        ttk.Label(summary_frame, text=f"Quantidade total em estoque: {total_stock:.2f}").grid(row=1, column=0, sticky="w")
        ttk.Label(summary_frame, text=f"Entradas: R$ {totals['entrada']:.2f}").grid(row=0, column=1, sticky="w")
        ttk.Label(summary_frame, text=f"Saídas: R$ {totals['saida']:.2f}").grid(row=1, column=1, sticky="w")
        ttk.Label(summary_frame, text=f"Saldo: R$ {totals['saldo']:.2f}").grid(row=2, column=1, sticky="w")
        # Alerta de estoque negativo
        if negative_count > 0:
            alert_text = f"Alerta: {negative_count} produto(s) com estoque negativo!"
            alert_lbl = ttk.Label(summary_frame, text=alert_text, foreground="red")
            alert_lbl.grid(row=2, column=0, sticky="w")
        # Espaçador
        ttk.Label(frame, text="").pack(pady=5)
        # Botões de navegação
        # Função para criar botão desabilitado se o usuário não tiver permissão
        def add_button(parent: tk.Widget, text: str, command: Optional[Callable], allowed: bool) -> None:
            btn = ttk.Button(parent, text=text, command=command)
            if not allowed:
                btn.state(["disabled"])
            btn.pack(fill="x", pady=4)

        # Verifica perfil
        role = self.current_role or "admin"
        is_admin = role == "admin" or role == "administrador"
        is_operator = is_admin or role == "operador"
        # Importar Notas (admin e operador)
        add_button(frame, "Importar Notas", self.show_import_window, is_operator)
        # Consultar estoque (todos)
        add_button(frame, "Consultar Estoque", self.show_inventory_window, True)
        # Relatório financeiro (todos)
        add_button(frame, "Relatório Financeiro", self.show_financial_window, True)
        # Histórico de movimentações (todos)
        add_button(frame, "Histórico de Movimentações", self.show_history_window, True)
        # Cadastro de produto (admin e operador)
        add_button(frame, "Cadastrar Produto", self.show_product_registration_window, is_operator)
        # Log de acessos (apenas admin)
        add_button(frame, "Log de Acessos", self.show_access_log_window, is_admin)
        # Logout
        add_button(frame, "Logout", self.logout, True)

    def clear_window(self) -> None:
        """Remove todos os widgets da janela."""
        for widget in self.master.winfo_children():
            widget.destroy()

    def logout(self) -> None:
        """Efetua logout do usuário atual e retorna à tela de login."""
        self.current_user = None
        self.current_role = None
        self.show_login_window()

    # ------------------------------------------------------------------
    # Importação avançada de notas
    # ------------------------------------------------------------------
    def show_import_window(self) -> None:
        """Exibe uma janela para seleção de arquivos XML/ZIP ou diretórios.

        O usuário pode escolher múltiplos arquivos e/ou um diretório para
        importar. Um resumo das notas adicionadas, duplicadas e erros é
        apresentado ao final.
        """
        win = tk.Toplevel(self.master)
        win.title("Importar Notas")
        win.geometry("600x400")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)
        # Lista de caminhos selecionados
        selected_files: List[str] = []
        selected_dirs: List[str] = []

        # Widgets para mostrar seleção
        listbox = tk.Listbox(frm, height=8)
        listbox.pack(fill="both", expand=True, pady=5)
        # Funções para selecionar arquivos e pastas
        def add_files() -> None:
            paths = filedialog.askopenfilenames(
                title="Selecionar arquivos XML ou ZIP",
                filetypes=(("Arquivos XML", "*.xml"), ("Arquivos ZIP", "*.zip"), ("Todos", "*.*")),
            )
            for p in paths:
                if p not in selected_files:
                    selected_files.append(p)
                    listbox.insert(tk.END, p)

        def add_directory() -> None:
            path = filedialog.askdirectory(title="Selecionar diretório contendo XMLs")
            if path and path not in selected_dirs:
                selected_dirs.append(path)
                listbox.insert(tk.END, f"[DIR] {path}")

        def clear_selection() -> None:
            selected_files.clear()
            selected_dirs.clear()
            listbox.delete(0, tk.END)

        # Barra de progressão opcional
        progress = ttk.Progressbar(frm, orient="horizontal", mode="determinate")
        progress.pack(fill="x", pady=5)
        progress['value'] = 0

        def perform_import() -> None:
            if not selected_files and not selected_dirs:
                messagebox.showwarning("Importação", "Nenhum arquivo ou diretório selecionado.")
                return
            # Inicializa contadores
            total_files = len(selected_files)
            # Estima número de XMLs em diretórios (aproximado)
            for d in selected_dirs:
                for _, _, files in os.walk(d):
                    total_files += sum(1 for f in files if f.lower().endswith('.xml'))
            inserted = 0
            duplicated = 0
            errors = 0
            processed = 0
            progress['maximum'] = max(1, total_files)
            # Importa arquivos individuais
            for fp in selected_files:
                if fp.lower().endswith('.zip'):
                    ins, dup, err = self._import_from_zip(fp)
                elif fp.lower().endswith('.xml'):
                    ins, dup, err = self._import_xml_file(fp)
                else:
                    continue
                inserted += ins
                duplicated += dup
                errors += err
                processed += ins + dup + err
                progress['value'] = processed
                win.update_idletasks()
            # Importa diretórios
            for d in selected_dirs:
                ins, dup, err = self._import_directory(d)
                inserted += ins
                duplicated += dup
                errors += err
                processed += ins + dup + err
                progress['value'] = processed
                win.update_idletasks()
            # Resultado
            parts = []
            if inserted:
                parts.append(f"{inserted} nota(s) importada(s)")
            if duplicated:
                parts.append(f"{duplicated} duplicada(s)")
            if errors:
                parts.append(f"{errors} erro(s)")
            msg = "; ".join(parts) if parts else "Nenhum arquivo processado."
            messagebox.showinfo("Importação Concluída", f"Importação finalizada: {msg}.")
            # Fecha janela após importação
            win.destroy()

        # Botões
        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Adicionar Arquivos", command=add_files).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Selecionar Pasta", command=add_directory).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Limpar Seleção", command=clear_selection).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Importar", command=perform_import).pack(side="right", padx=5)

    def _import_directory(self, dir_path: str) -> Tuple[int, int, int]:
        """Importa todos os arquivos XML dentro de um diretório recursivamente.

        :return: tupla (inseridos, duplicados, erros)
        """
        inserted = 0
        duplicated = 0
        errors = 0
        for root_dir, _, files in os.walk(dir_path):
            for fname in files:
                if fname.lower().endswith('.xml'):
                    fpath = os.path.join(root_dir, fname)
                    ins, dup, err = self._import_xml_file(fpath)
                    inserted += ins
                    duplicated += dup
                    errors += err
        return inserted, duplicated, errors

    # ------------------------------------------------------------------
    # Cadastro manual de produtos
    # ------------------------------------------------------------------
    def show_product_registration_window(self) -> None:
        """Exibe uma janela para cadastrar um novo produto e ajustar estoque."""
        win = tk.Toplevel(self.master)
        win.title("Cadastrar Produto")
        win.geometry("400x250")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Código do Produto:").grid(row=0, column=0, sticky="e")
        code_entry = ttk.Entry(frm)
        code_entry.grid(row=0, column=1, pady=5)
        ttk.Label(frm, text="Descrição:").grid(row=1, column=0, sticky="e")
        desc_entry = ttk.Entry(frm)
        desc_entry.grid(row=1, column=1, pady=5)
        ttk.Label(frm, text="Quantidade Inicial:").grid(row=2, column=0, sticky="e")
        qty_entry = ttk.Entry(frm)
        qty_entry.grid(row=2, column=1, pady=5)
        result_lbl = ttk.Label(frm, text="")
        result_lbl.grid(row=4, column=0, columnspan=2, pady=5)
        def save_product() -> None:
            code = code_entry.get().strip()
            desc = desc_entry.get().strip()
            qty_text = qty_entry.get().strip()
            if not code or not desc:
                messagebox.showerror("Erro", "Código e descrição são obrigatórios.")
                return
            try:
                qty = float(qty_text) if qty_text else 0.0
            except ValueError:
                messagebox.showerror("Erro", "Quantidade inválida.")
                return
            # Adiciona ou atualiza produto
            self.db.add_or_update_product(code, desc)
            # Ajusta estoque com uma entrada
            if qty != 0:
                self.db.update_inventory(code, qty, "entrada")
            self.db.conn.commit()
            result_lbl.config(text="Produto cadastrado/atualizado com sucesso.")
            # Limpa campos
            code_entry.delete(0, tk.END)
            desc_entry.delete(0, tk.END)
            qty_entry.delete(0, tk.END)
        ttk.Button(frm, text="Salvar", command=save_product).grid(row=3, column=0, columnspan=2, pady=10)

    # ------------------------------------------------------------------
    # Log de acessos
    # ------------------------------------------------------------------
    def show_access_log_window(self) -> None:
        """Mostra uma janela com o log de tentativas de login (somente admin)."""
        # Apenas administradores podem acessar
        role = self.current_role or ""
        if role not in ("admin", "administrador"):
            messagebox.showwarning("Acesso negado", "Somente administradores podem ver o log de acessos.")
            return
        win = tk.Toplevel(self.master)
        win.title("Log de Acessos")
        win.geometry("700x400")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)
        # Cabeçalhos
        columns = ("Usuário", "Data/Hora", "Sucesso")
        tree = ttk.Treeview(frm, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=200 if col != "Sucesso" else 80, anchor="center")
        # Scrollbar
        scrollbar = ttk.Scrollbar(frm, orient="vertical", command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        tree.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        frm.rowconfigure(1, weight=1)
        frm.columnconfigure(0, weight=1)
        # Preenche dados
        logs = self.db.get_access_logs()
        for username, ts, success in logs:
            status = "Sim" if success == 1 or success is True else "Não"
            tree.insert("", "end", values=(username, ts.replace("T", " "), status))
        # Exportação opcional
        def export_logs() -> None:
            if not HAS_PANDAS:
                messagebox.showerror("Exportação indisponível", "A biblioteca pandas não está disponível.")
                return
            import pandas as pd
            df = pd.DataFrame(logs, columns=["Usuário", "Data/Hora", "Sucesso"])
            file_path = filedialog.asksaveasfilename(
                title="Salvar log de acessos",
                defaultextension=".csv",
                filetypes=(("CSV", "*.csv"), ("Excel", "*.xlsx"), ("PDF", "*.pdf")),
            )
            if not file_path:
                return
            try:
                ext = os.path.splitext(file_path)[1].lower()
                if ext == ".xlsx":
                    df.to_excel(file_path, index=False)
                elif ext == ".pdf":
                    export_dataframe_to_pdf(df, file_path, title="Log de Acessos")
                else:
                    df.to_csv(file_path, index=False, sep=';')
                messagebox.showinfo("Exportação", f"Log salvo em {file_path}.")
            except Exception as e:
                messagebox.showerror("Erro na exportação", f"Não foi possível exportar: {e}")
        ttk.Button(frm, text="Exportar", command=export_logs).grid(row=0, column=0, sticky="w", pady=5)

    def import_notes(self) -> None:
        """Permite que o usuário selecione arquivos XML ou ZIP e importa as notas.

        Mostra um resumo indicando quantas notas foram inseridas, quantas já existiam
        (duplicadas) e quantos erros ocorreram.
        """
        file_paths = filedialog.askopenfilenames(
            title="Selecione arquivos XML ou ZIP",
            filetypes=(
                ("Arquivos XML", "*.xml"),
                ("Arquivos ZIP", "*.zip"),
                ("Todos os arquivos", "*.*"),
            ),
        )
        if not file_paths:
            return
        inserted = 0
        duplicated = 0
        errors = 0
        for path in file_paths:
            if path.lower().endswith('.zip'):
                ins, dup, err = self._import_from_zip(path)
            elif path.lower().endswith('.xml'):
                ins, dup, err = self._import_xml_file(path)
            else:
                continue
            inserted += ins
            duplicated += dup
            errors += err
        # Construir mensagem de resumo
        parts = []
        if inserted:
            parts.append(f"{inserted} nota(s) importada(s)")
        if duplicated:
            parts.append(f"{duplicated} nota(s) duplicada(s) ignorada(s)")
        if errors:
            parts.append(f"{errors} arquivo(s) com erro")
        msg = "; ".join(parts) if parts else "Nenhum arquivo processado."
        messagebox.showinfo(
            "Importação Concluída",
            f"Importação finalizada. {msg}",
        )

    def _import_from_zip(self, zip_path: str) -> Tuple[int, int, int]:
        """Extrai e importa notas de um arquivo ZIP.

        :param zip_path: Caminho do arquivo ZIP
        :return: tupla (inseridos, duplicados, erros)
        """
        inserted = 0
        duplicated = 0
        errors = 0
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Extrai para um diretório temporário
            with tempfile.TemporaryDirectory() as tmpdir:
                zf.extractall(tmpdir)
                for root_dir, _, files in os.walk(tmpdir):
                    for fname in files:
                        if fname.lower().endswith('.xml'):
                            fpath = os.path.join(root_dir, fname)
                            ins, dup, err = self._import_xml_file(fpath)
                            inserted += ins
                            duplicated += dup
                            errors += err
        return inserted, duplicated, errors

    def _import_xml_file(self, xml_path: str) -> Tuple[int, int, int]:
        """Importa uma única nota XML.

        :param xml_path: Caminho do arquivo XML
        :return: tupla (inseridos, duplicados, erros)
        """
        try:
            parsed = parse_xml_file(xml_path)
            inserted = self.db.insert_note(parsed)
            return (1 if inserted else 0, 0 if inserted else 1, 0)
        except Exception as e:
            messagebox.showerror(
                "Erro ao importar XML",
                f"Não foi possível importar {os.path.basename(xml_path)}:\n{e}",
            )
            return (0, 0, 1)

    def show_inventory_window(self) -> None:
        """Exibe uma janela com o estoque atual."""
        win = tk.Toplevel(self.master)
        win.title("Estoque Atual")
        win.geometry("600x400")
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        # Tabela de estoque
        columns = ("Código", "Descrição", "Quantidade")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=200 if col != "Quantidade" else 100, anchor="center")
        # Scrollbar
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        # Preenche dados
        # Configura tag para valores negativos
        tree.tag_configure("negativo", foreground="red")
        for code, desc, qty in self.db.query_inventory():
            tags = ("negativo",) if qty < 0 else ()
            tree.insert("", "end", values=(code, desc, f"{qty:.2f}"), tags=tags)

    def show_financial_window(self) -> None:
        """Abre uma janela para selecionar período e visualizar o balanço.

        Esta janela permite calcular o total de entradas, saídas e saldo líquido
        por período, exportar os dados em CSV/Excel/PDF e exibir um gráfico
        opcional comparando os valores de entrada, saída e saldo.
        """
        win = tk.Toplevel(self.master)
        win.title("Relatório Financeiro")
        win.geometry("500x380")
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        # Campos de data
        ttk.Label(frame, text="Data inicial (AAAA-MM-DD):").grid(row=0, column=0, sticky="e")
        start_entry = ttk.Entry(frame)
        start_entry.grid(row=0, column=1, pady=5)
        ttk.Label(frame, text="Data final (AAAA-MM-DD):").grid(row=1, column=0, sticky="e")
        end_entry = ttk.Entry(frame)
        end_entry.grid(row=1, column=1, pady=5)
        result_lbl = ttk.Label(frame, text="", justify="left")
        result_lbl.grid(row=4, column=0, columnspan=3, pady=10)

        # Variável para armazenar último resumo calculado
        summary: Dict[str, float] = {"entrada": 0.0, "saida": 0.0, "saldo": 0.0}
        current_notes: List[Dict[str, any]] = []

        def calculate() -> None:
            """Calcula os totais de notas para o período selecionado."""
            s_date = start_entry.get().strip()
            e_date = end_entry.get().strip()
            try:
                start_dt = datetime.fromisoformat(s_date) if s_date else None
            except Exception:
                messagebox.showerror("Data inválida", "Data inicial inválida. Use o formato AAAA-MM-DD.")
                return
            try:
                end_dt = datetime.fromisoformat(e_date) if e_date else None
            except Exception:
                messagebox.showerror("Data inválida", "Data final inválida. Use o formato AAAA-MM-DD.")
                return
            # Atualiza resumo
            nonlocal summary, current_notes
            summary = self.db.query_financial_summary(start_dt, end_dt)
            result_lbl.config(
                text=(
                    f"Entradas: R$ {summary['entrada']:.2f}\n"
                    f"Saídas:   R$ {summary['saida']:.2f}\n"
                    f"Saldo:    R$ {summary['saldo']:.2f}"
                )
            )
            # Também armazena notas detalhadas para exportação
            current_notes = self.db.query_notes(start_dt, end_dt)

        ttk.Button(frame, text="Calcular", command=calculate).grid(row=2, column=0, columnspan=3, pady=10)

        # Botão para exibir gráfico
        def show_chart() -> None:
            """Exibe um gráfico de barras comparando entradas, saídas e saldo."""
            # Recalcula se necessário
            if not (summary['entrada'] or summary['saida'] or summary['saldo']):
                calculate()
            try:
                import matplotlib.pyplot as plt
                from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            except ImportError:
                messagebox.showerror("Biblioteca faltando", "Matplotlib não está disponível.")
                return
            # Dados para gráfico
            categories = ["Entradas", "Saídas", "Saldo"]
            values = [summary['entrada'], summary['saida'], summary['saldo']]
            # Cria figura
            fig, ax = plt.subplots()
            ax.bar(categories, values)
            ax.set_title("Resumo Financeiro")
            # Mostra gráfico em nova janela Tkinter
            chart_win = tk.Toplevel(win)
            chart_win.title("Gráfico Financeiro")
            canvas = FigureCanvasTkAgg(fig, master=chart_win)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            plt.close(fig)

        chart_btn = ttk.Button(frame, text="Exibir Gráfico", command=show_chart)
        chart_btn.grid(row=3, column=0, pady=5)

        # Exportação (CSV, Excel, PDF)
        def export_report() -> None:
            if not current_notes:
                messagebox.showinfo("Exportação", "Nenhuma nota para exportar.")
                return
            if not HAS_PANDAS:
                messagebox.showerror(
                    "Exportação indisponível", "A biblioteca pandas não está disponível.")
                return
            import pandas as pd  # Garantir import local
            df = pd.DataFrame(current_notes)
            # Pergunta formato
            file_path = filedialog.asksaveasfilename(
                title="Salvar relatório",
                defaultextension=".csv",
                filetypes=(
                    ("CSV", "*.csv"),
                    ("Excel", "*.xlsx"),
                    ("PDF", "*.pdf"),
                ),
            )
            if not file_path:
                return
            try:
                ext = os.path.splitext(file_path)[1].lower()
                if ext == ".xlsx":
                    df.to_excel(file_path, index=False)
                elif ext == ".pdf":
                    # Exporta para PDF usando matplotlib
                    export_dataframe_to_pdf(df, file_path, title="Relatório Financeiro")
                else:
                    df.to_csv(file_path, index=False, sep=';')
                messagebox.showinfo("Exportação", f"Relatório salvo em {file_path}.")
            except Exception as e:
                messagebox.showerror("Erro na exportação", f"Não foi possível exportar: {e}")

        ttk.Button(frame, text="Exportar", command=export_report).grid(row=3, column=1, pady=5)

    def show_history_window(self) -> None:
        """Abre a janela de histórico com filtros de período, tipo, produto e entidade."""
        win = tk.Toplevel(self.master)
        win.title("Histórico de Movimentações")
        win.geometry("900x550")
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        # Filtros de período
        ttk.Label(frame, text="Data inicial (AAAA-MM-DD):").grid(row=0, column=0, sticky="e")
        start_entry = ttk.Entry(frame)
        start_entry.grid(row=0, column=1, pady=5, sticky="w")
        ttk.Label(frame, text="Data final (AAAA-MM-DD):").grid(row=1, column=0, sticky="e")
        end_entry = ttk.Entry(frame)
        end_entry.grid(row=1, column=1, pady=5, sticky="w")
        # Filtro de tipo
        ttk.Label(frame, text="Tipo:").grid(row=0, column=2, sticky="e")
        type_combo = ttk.Combobox(frame, values=("", "entrada", "saida"), state="readonly")
        type_combo.grid(row=0, column=3, pady=5, sticky="w")
        type_combo.set("")
        # Filtro de produto
        ttk.Label(frame, text="Produto:").grid(row=1, column=2, sticky="e")
        # Carrega lista de produtos (somente códigos) com descrições
        products = self.db.get_all_products()
        prod_values = [""] + [f"{code} - {desc}" for code, desc in products]
        prod_combo = ttk.Combobox(frame, values=prod_values, state="readonly")
        prod_combo.grid(row=1, column=3, pady=5, sticky="w")
        prod_combo.set("")
        # Filtro de entidade
        ttk.Label(frame, text="Entidade:").grid(row=2, column=0, sticky="e")
        entities = self.db.get_all_entities()
        ent_values = [""] + [name for _, name in entities]
        ent_combo = ttk.Combobox(frame, values=ent_values, state="readonly")
        ent_combo.grid(row=2, column=1, pady=5, sticky="w")
        ent_combo.set("")
        # Label de resultados
        result_info = ttk.Label(frame, text="")
        result_info.grid(row=3, column=0, columnspan=4, sticky="w", pady=5)

        # Tabela de resultados
        columns = ("Data", "Tipo", "Entidade", "Total")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=200 if col != "Total" else 120, anchor="center")
        # Scrollbar
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        # Posiciona tabela
        tree.grid(row=4, column=0, columnspan=4, sticky="nsew")
        scrollbar.grid(row=4, column=4, sticky="ns")
        # Permite crescimento
        frame.rowconfigure(4, weight=1)
        frame.columnconfigure(3, weight=1)

        # Função para filtrar resultados
        def refresh() -> None:
            s_date = start_entry.get().strip()
            e_date = end_entry.get().strip()
            note_t = type_combo.get().strip() or None
            # Converte datas
            try:
                start_dt = datetime.fromisoformat(s_date) if s_date else None
            except Exception:
                messagebox.showerror("Data inválida", "Data inicial inválida. Use AAAA-MM-DD.")
                return
            try:
                end_dt = datetime.fromisoformat(e_date) if e_date else None
            except Exception:
                messagebox.showerror("Data inválida", "Data final inválida. Use AAAA-MM-DD.")
                return
            # Produto
            prod_sel = prod_combo.get()
            product_code = None
            if prod_sel:
                # prod_sel format: "code - description"
                product_code = prod_sel.split(" - ")[0]
            # Entidade
            ent_sel = ent_combo.get()
            entity_id = None
            if ent_sel:
                # Find id by name
                for eid, name in entities:
                    if name == ent_sel:
                        entity_id = eid
                        break
            # Consulta
            notes = self.db.query_notes_filtered(
                start_dt, end_dt, note_t, product_code, entity_id
            )
            # Atualiza tabela
            tree.delete(*tree.get_children())
            for note in notes:
                tree.insert(
                    "",
                    "end",
                    iid=note["id"],
                    values=(note["date"][:10], note["type"], note["entity"], f"{note['total']:.2f}"),
                )
            # Atualiza label de contagem
            result_info.config(text=f"Exibindo {len(notes)} movimentação(ões)")

        # Função para limpar filtros
        def clear_filters() -> None:
            start_entry.delete(0, tk.END)
            end_entry.delete(0, tk.END)
            type_combo.set("")
            prod_combo.set("")
            ent_combo.set("")
            tree.delete(*tree.get_children())
            result_info.config(text="")

        # Botões de ação
        ttk.Button(frame, text="Filtrar", command=refresh).grid(row=3, column=2, pady=5, sticky="e")
        ttk.Button(frame, text="Limpar Filtros", command=clear_filters).grid(row=3, column=3, pady=5, sticky="w")

        # Exportação
        def export_history() -> None:
            # Gera DataFrame das notas atualmente exibidas
            if not HAS_PANDAS:
                messagebox.showerror("Exportação indisponível", "A biblioteca pandas não está disponível.")
                return
            items = []
            for iid in tree.get_children():
                vals = tree.item(iid)["values"]
                items.append({"Data": vals[0], "Tipo": vals[1], "Entidade": vals[2], "Total": vals[3]})
            if not items:
                messagebox.showinfo("Exportação", "Nenhuma movimentação para exportar.")
                return
            import pandas as pd
            df = pd.DataFrame(items)
            file_path = filedialog.asksaveasfilename(
                title="Salvar histórico",
                defaultextension=".csv",
                filetypes=(("CSV", "*.csv"), ("Excel", "*.xlsx"), ("PDF", "*.pdf")),
            )
            if not file_path:
                return
            try:
                ext = os.path.splitext(file_path)[1].lower()
                if ext == ".xlsx":
                    df.to_excel(file_path, index=False)
                elif ext == ".pdf":
                    export_dataframe_to_pdf(df, file_path, title="Histórico de Movimentações")
                else:
                    df.to_csv(file_path, index=False, sep=';')
                messagebox.showinfo("Exportação", f"Histórico salvo em {file_path}.")
            except Exception as e:
                messagebox.showerror("Erro na exportação", f"Não foi possível exportar: {e}")

        ttk.Button(frame, text="Exportar", command=export_history).grid(row=3, column=0, pady=5, sticky="w")

        # Duplo clique para ver itens da nota
        def on_double_click(event: tk.Event) -> None:
            item_id = tree.focus()
            if not item_id:
                return
            try:
                note_id = int(item_id)
            except ValueError:
                return
            items = self.db.get_note_items(note_id)
            self._show_items_window(items)
        tree.bind("<Double-1>", on_double_click)

    def _show_items_window(self, items: List[Dict[str, any]]) -> None:
        """Mostra uma janela com os itens de uma nota."""
        win = tk.Toplevel(self.master)
        win.title("Itens da Nota")
        win.geometry("600x400")
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        columns = ("Código", "Descrição", "Quantidade", "Preço Unit.", "Total")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=110 if col != "Descrição" else 200, anchor="center")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        for item in items:
            tree.insert(
                "",
                "end",
                values=(
                    item["code"],
                    item["description"],
                    f"{item['quantity']:.2f}",
                    f"{item['unit_price']:.2f}",
                    f"{item['total']:.2f}",
                ),
            )


def main() -> None:
    """Ponto de entrada do programa."""
    root = tk.Tk()
    # Definimos um estilo mais agradável
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
    NFeAppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()