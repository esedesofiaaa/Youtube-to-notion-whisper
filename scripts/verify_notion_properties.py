#!/usr/bin/env python3
"""
Script para verificar que las propiedades necesarias existen en las bases de datos de Notion.
Ejecutar antes de usar las nuevas funcionalidades.
"""

import os
from dotenv import load_dotenv
from notion_client import Client

# Cargar variables de entorno
load_dotenv()

NOTION_TOKEN = os.getenv('NOTION_TOKEN')
PARADISE_ISLAND_DB_ID = os.getenv('PARADISE_ISLAND_DB_ID')
DOCS_VIDEOS_DB_ID = os.getenv('DOCS_VIDEOS_DB_ID')

# Propiedades requeridas
REQUIRED_PROPERTIES = {
    "Audio File Link": "url",
    "Transcript File": "files",
    "Transcript SRT File": "files"
}

def check_database_properties(client, database_id, database_name):
    """
    Verificar que una base de datos tenga las propiedades requeridas.
    
    Args:
        client: Cliente de Notion
        database_id: ID de la base de datos
        database_name: Nombre de la base de datos (para logging)
    """
    print(f"\n{'='*60}")
    print(f"Verificando: {database_name}")
    print(f"{'='*60}")
    
    try:
        # Obtener información de la base de datos
        database = client.databases.retrieve(database_id=database_id)
        properties = database.get("properties", {})
        
        print(f"✅ Base de datos accesible: {database_id}")
        print(f"\nPropiedades encontradas: {len(properties)}")
        
        # Verificar cada propiedad requerida
        missing_properties = []
        wrong_type_properties = []
        
        for prop_name, expected_type in REQUIRED_PROPERTIES.items():
            if prop_name in properties:
                actual_type = properties[prop_name].get("type")
                if actual_type == expected_type:
                    print(f"  ✅ {prop_name} ({expected_type})")
                else:
                    print(f"  ⚠️  {prop_name} (esperado: {expected_type}, encontrado: {actual_type})")
                    wrong_type_properties.append((prop_name, expected_type, actual_type))
            else:
                print(f"  ❌ {prop_name} - NO ENCONTRADA")
                missing_properties.append(prop_name)
        
        # Resumen
        if not missing_properties and not wrong_type_properties:
            print(f"\n✅ Todas las propiedades requeridas están correctas!")
        else:
            print(f"\n⚠️  PROBLEMAS ENCONTRADOS:")
            if missing_properties:
                print(f"\n  Propiedades faltantes:")
                for prop in missing_properties:
                    print(f"    - {prop} (tipo: {REQUIRED_PROPERTIES[prop]})")
                print(f"\n  Por favor, agrega estas propiedades manualmente en Notion:")
                print(f"  https://www.notion.so/{database_id.replace('-', '')}")
            
            if wrong_type_properties:
                print(f"\n  Propiedades con tipo incorrecto:")
                for prop, expected, actual in wrong_type_properties:
                    print(f"    - {prop}: esperado '{expected}', encontrado '{actual}'")
        
        return len(missing_properties) == 0 and len(wrong_type_properties) == 0
        
    except Exception as e:
        print(f"❌ Error al acceder a la base de datos: {e}")
        return False


def main():
    """Función principal."""
    print("\n" + "="*60)
    print("VERIFICADOR DE PROPIEDADES DE NOTION")
    print("="*60)
    
    if not NOTION_TOKEN:
        print("❌ NOTION_TOKEN no encontrado en variables de entorno")
        return
    
    print("\n✅ Token de Notion encontrado")
    
    # Crear cliente de Notion
    client = Client(auth=NOTION_TOKEN)
    
    # Verificar bases de datos
    results = []
    
    if PARADISE_ISLAND_DB_ID:
        results.append(check_database_properties(
            client, 
            PARADISE_ISLAND_DB_ID, 
            "Paradise Island Videos Database"
        ))
    else:
        print("\n⚠️  PARADISE_ISLAND_DB_ID no configurado")
    
    if DOCS_VIDEOS_DB_ID:
        results.append(check_database_properties(
            client, 
            DOCS_VIDEOS_DB_ID, 
            "Docs Videos Database"
        ))
    else:
        print("\n⚠️  DOCS_VIDEOS_DB_ID no configurado")
    
    # Resumen final
    print("\n" + "="*60)
    print("RESUMEN FINAL")
    print("="*60)
    
    if all(results):
        print("✅ Todas las bases de datos están correctamente configuradas!")
        print("\nPuedes proceder a usar las nuevas funcionalidades.")
    else:
        print("⚠️  Algunas bases de datos necesitan configuración adicional.")
        print("\nPor favor, agrega las propiedades faltantes en Notion antes de continuar.")
        print("\nInstrucciones:")
        print("1. Abre la base de datos en Notion")
        print("2. Haz clic en '+ New property' o el botón '+' en la esquina superior derecha")
        print("3. Agrega las propiedades con los siguientes tipos:")
        print("   - Audio File Link: tipo 'URL'")
        print("   - Transcript File: tipo 'Files & Media'")
        print("   - Transcript SRT File: tipo 'Files & Media'")
    
    print("\n")


if __name__ == "__main__":
    main()
