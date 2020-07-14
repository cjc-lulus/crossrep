import os
from datetime import datetime
import glob
from os import listdir
from os.path import isfile, join
import fnmatch

def list_scripts(migHome, objectType = ''):
    list = []
    '''rootfolder = migHome + "scripts/"
    for folder in listdir(rootfolder):
        print(rootfolder + folder)
        if not (isfile(rootfolder + folder)) :
            for subfolder in listdir(rootfolder + folder):
                subfolder_path = rootfolder + folder + "/" + subfolder + "/";
                if not (isfile(subfolder_path)):
                    for file in listdir(subfolder_path):
                        fullpath = subfolder_path + file
                        if isfile(fullpath) and fnmatch.fnmatch(fullpath, '*.sql'):
                            list.append(fullpath)
    '''
    root_folder = migHome + "scripts/"
    if len(objectType) > 0:
        root_folder += objectType + "/"
    for root, dirs, files in os.walk(root_folder):
        for file in files:
            if file.endswith(".sql"):
                # sort_on = "key2"
                dict = {}
                dict['file'] = file
                dict['path'] = root
                list.append(dict)
    return sorted(list, key = lambda i: i['file'])


def upload_scripts(mode, filedict, cursor, failed_statements):
    # open file
    filename = os.path.join(filedict['path'], filedict['file'])
    f = open(filename, "r")
    if f.mode == "r":
        contents = f.read()
        batch_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # cursor.execute("CALL mei_db_crossrep.mei_tgt_crossrep.parse_sql_script(%s, %s, %s)", (batch_id, filename, contents))
        build_ddl_statememts(mode, batch_id, contents, filename, cursor, failed_statements)
        f.close()


def build_dll_statememts(mode, batch_id, long_sql_text, file_path, cursor, failed_statements):
    sql_statements = long_sql_text.split(";")
    retry_list = []
    cur_database = ""
    cur_schema = ""
    table_keyword = "create TABLE if not exists "
    schema_keyword = "create schema if not exists "
    db_keyword = "create database if not exists "
    use_db_keyword = "use database "
    use_schema_keyword = "use schema "
    sp_keyword = "create PROCEDURE if not exists "
    view_keyword = "create view if not exists "
    mview_keyword = "create materialized view if not exists "
    fn_keyword = "create FUNCTION if not exists "
    file_format_keyword = "create FILE FORMAT if not exists "
    seq_keyword = "create sequence if not exists "
    total_statement = 0
    i = 0;
    while i < len(sql_statements)-1:
        statement = sql_statements[i].lstrip()
        if len(statement) == 0:
            continue

        statement_type = 'unknown'
        if statement.startswith(db_keyword):
            statement_type = db_keyword.upper()
        elif statement.startswith(schema_keyword):
            statement_type = schema_keyword.upper()
        elif statement.startswith(table_keyword):
            statement_type = table_keyword.upper()
        elif statement.startswith(view_keyword):
            statement_type = view_keyword.upper()
        elif statement.startswith(mview_keyword):
            statement_type = mview_keyword.upper()
        elif statement.startswith(file_format_keyword):
            statement_type = file_format_keyword.upper()
        elif statement.startswith(use_db_keyword):
            statement_type = use_db_keyword.upper()
            cur_database = statement[len(use_db_keyword)::]
        elif statement.startswith(use_schema_keyword):
            statement_type = use_schema_keyword.upper()
            cur_schema = statement[len(use_schema_keyword)::]
        elif statement.startswith(seq_keyword):
            statement_type = seq_keyword.upper()
        elif statement.startswith(sp_keyword) or statement.startswith(fn_keyword):
            if statement.startswith(sp_keyword):
                statement_type = sp_keyword.upper()
            else:
                statement_type = fn_keyword.upper()
            statement = statement + "\n"
            while i + 1 < len(sql_statements):
                i = i + 1
                if sql_statements[i].lstrip().startswith("create "):
                    i = i - 1
                    break
                else:
                    statement = statement + sql_statements[i] + ";"
        print(statement)
        try:
            if mode == 'DR_TEST':
                if statement_type == 'unknown':
                    failed_statements.append(
                        {"statement_type": statement_type, "cur_database": cur_database, "cur_schema": cur_schema,
                         "statement": statement, "file_path": file_path, "error": "Bad Statement"})
            elif mode == 'DR':
                cursor.execute(statement)
        except:
            failed_statements.append({"statement_type": statement_type, "cur_database": cur_database, "cur_schema": cur_schema,
                              "statement": statement, "file_path": file_path})
        # stmt = snowflake.createStatement(
        # {
        #    sqlText: "INSERT INTO source_scripts (BATCH_ID,SCRIPT_FILE_NAME_PATH, SQL_TEXT, STATEMENT_TYPE, USE_DATABASE_NAME, USE_SCHEMA_NAME) VALUES (?, ?, ?, ?, ?, ?);",
        #    binds: [BATCH_ID, FILE_PATH, statement, statement_type, cur_database, cur_schema]
        # }

        # result_set1 = stmt.execute();
        total_statement = total_statement + 1
        i = i + 1


def retry_failed_statements(cursor, failed_statements):
    next_retry = []
    retry_list = failed_statements
    cur_schema = ''
    cur_database = ''
    while len(retry_list) > 0:
        for item in retry_list:
            if item["cur_database"] != cur_database:
                cur_database = item["cur_database"]
                cursor.execute('USE DATABASE "' + cur_database + '"')
            if item["cur_schema"] != cur_schema:
                cur_schema = item["cur_schema"]
                cursor.execute('USE SCHEMA "' + cur_schema + '"')
            try:
                cursor.execute(item["statement"])
                print("Retry succeeded --->" + item["statement"])
            except e:
                item["error"] = str(e)
                next_retry.append(item)
        if len(retry_list) == len(next_retry):
            # this means no more statement can be run successfully
            return next_retry
        else:
            retry_list = next_retry
            next_retry = []
    return next_retry
