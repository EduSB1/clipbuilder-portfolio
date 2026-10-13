import json
import os
import sys

# Adiciona o diretório atual ao PYTHONPATH para importar os módulos da aplicação
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.admin.models import AiTool
from app.database import SessionLocal


def main():
    print("Atualizando a ferramenta 'Transcrição Sincronizada com Frames'...")
    with SessionLocal() as db:
        tool = db.query(AiTool).filter(AiTool.name == "Transcrição Sincronizada com Frames").first()
        if not tool:
            print("Ferramenta não encontrada no banco de dados!")
            return

        tool.model_name = "models/gemini-2.5-flash"
        tool.triggers = json.dumps(["on_frame_capture"])
        db.commit()
        print("Ferramenta atualizada com sucesso:")
        print(f"  - Novo modelo: {tool.model_name}")
        print(f"  - Novo trigger: {tool.triggers}")

if __name__ == "__main__":
    main()
