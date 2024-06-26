# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import random
import string
import time
from typing import Generator

import pytest
import sqlalchemy
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.human import HumanMessage

from langchain_google_el_carro import ElCarroEngine
from langchain_google_el_carro.chat_message_history import ElCarroChatMessageHistory

db_host = os.environ["DB_HOST"]
db_port = int(os.environ["DB_PORT"])
db_name = os.environ["DB_NAME"]
db_user = os.environ["DB_USER"]
db_password = os.environ["DB_PASSWORD"]


@pytest.fixture(name="memory_engine")
def setup_engine() -> Generator:
    elcarro_engine = ElCarroEngine.from_instance(
        db_host,
        db_port,
        db_name,
        db_user,
        db_password,
    )
    yield elcarro_engine


@pytest.fixture(name="temporary_table")
def temporary_table(memory_engine: ElCarroEngine) -> Generator:
    """
    Prepare a random table name and delete it if it exists.
    Delete the table on fixture cleanup.
    """
    random_suffix = "".join(random.choices(string.ascii_lowercase, k=6))
    table_name = f"message_store_{random_suffix}"
    try:
        memory_engine.drop_chat_history_table(table_name)
    except sqlalchemy.exc.NoSuchTableError as e:
        pass

    yield table_name

    # Cleanup
    try:
        memory_engine.drop_chat_history_table(table_name)
    except sqlalchemy.exc.NoSuchTableError as e:
        print(e)


def test_chat_message_history(
    memory_engine: ElCarroEngine, temporary_table: str
) -> None:
    table_name = temporary_table

    # create a new table
    memory_engine.init_chat_history_table(table_name)
    history = ElCarroChatMessageHistory(
        elcarro_engine=memory_engine, session_id="test", table_name=table_name
    )
    message = "hi " + string.printable
    history.add_user_message(message)
    history.add_ai_message("whats up?")
    messages = history.messages

    # verify messages are correct
    assert messages[0].content == message
    assert type(messages[0]) is HumanMessage
    assert messages[1].content == "whats up?"
    assert type(messages[1]) is AIMessage

    # verify clear() clears message history
    history.clear()
    assert len(history.messages) == 0


def test_chat_message_history_table_does_not_exist(
    memory_engine: ElCarroEngine,
) -> None:
    """Test that ElCarroChatMessageHistory fails if table does not exist."""

    with pytest.raises(AttributeError) as exc_info:
        ElCarroChatMessageHistory(
            elcarro_engine=memory_engine, session_id="test", table_name="missing_table"
        )


def test_chat_message_history_table_malformed_schema(
    memory_engine: ElCarroEngine, temporary_table: str
) -> None:
    """Test that ElCarroChatMessageHistory fails if schema is malformed."""
    malformed_table_name = temporary_table

    create_table_query = f"""CREATE TABLE {malformed_table_name} (
              id NUMBER GENERATED BY DEFAULT AS IDENTITY (START WITH 1),
              session_id VARCHAR2(128) NOT NULL,
              data CLOB NOT NULL,
              PRIMARY KEY (id)
            )"""

    with memory_engine.connect() as conn:
        conn.execute(sqlalchemy.text(create_table_query))
        conn.commit()

    with pytest.raises(IndexError):
        ElCarroChatMessageHistory(
            elcarro_engine=memory_engine,
            session_id="test",
            table_name=malformed_table_name,
        )
