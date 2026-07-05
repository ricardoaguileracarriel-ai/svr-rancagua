import sqlite3
con = sqlite3.connect('modulos/archivo_svr.db')
print("Integridad:", con.execute("PRAGMA integrity_check").fetchall())