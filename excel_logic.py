import pandas as pd
import os

def generar_compendio_final(lista_archivos, nombre_salida):
    base_path = 'uploads/'
    dfs = []
    
    for archivo in lista_archivos:
        path = os.path.join(base_path, archivo)
        if os.path.exists(path):
            df = pd.read_excel(path)
            dfs.append(df)
    
    if dfs:
        compendio = pd.concat(dfs, ignore_index=True)
        ruta_salida = os.path.join(base_path, nombre_salida)
        compendio.to_excel(ruta_salida, index=False)
        return nombre_salida
    return None