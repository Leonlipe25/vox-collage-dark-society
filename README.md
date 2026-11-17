# 🎬 Vox Collage — Dark Society Edition

**Transforme qualquer tema ou roteiro em um documentário estilo Colagem de Papel da Vox (*Vox-Style Paper-Collage Explainer*) — 100% automatizado por Agente IA (Antigravity / Claude Code / Cursor) + OpenCV + FFmpeg.**

![License: MIT](https://img.shields.io/badge/License-MIT-black.svg) ![Engine: Local OpenCV + FFmpeg](https://img.shields.io/badge/Engine-OpenCV%20%2B%20FFmpeg-d92b2b.svg) ![TTS: DarkPlanner | Google TTS](https://img.shields.io/badge/TTS-DarkPlanner%20%7C%20Google%20TTS-0e8a5f.svg)

---

## 🧩 O que é este repositório?

Este projeto é uma **Agent Skill** completa que produz vídeos *faceless* de alta retenção no estilo **Editorial Motion Collage** (popularizado pela **Vox** e **Johnny Harris**):
- **Gravuras de Colagem Física:** Pôsteres gerados via **Nano Banana** com textura de papel rasgado à mão, recortes de jornal em *halftone*, fita crepe, alfinetes, barbante vermelho e manchetes tipográficas.
- **Animação Real dos Objetos da Gravura (`scripts/vox_animator.py`):** Em vez de apenas dar zoom estático na foto inteira, o motor em **OpenCV (`cv2.inpaint`) + NumPy + Pillow + FFmpeg** recorta os objetos de dentro da própria gravura, reconstrói o fundo de papel/quadriculado por trás deles e anima cada peça em **stop-motion (10 fps)** com física elástica (`ease_out_back`), ponteiros girando, setas de gráficos crescendo, rotas pulsando no mapa e *camera shake*.
- **Cadência Dinâmica de Retenção:** Cortes rápidos a cada **3.5 a 5 segundos**, intercalando planos gerais (*Wide*) com cortes de detalhe (*Cut-ins*) sincronizados à fala.
- **Legendas Nativas em Recorte de Papel (`scripts/text_overlay.py`):** Legendas sincronizadas ao `.srt` com borda colorida extraída automaticamente da paleta de cada gravura.

---

## ⚠️ PRÉ-REQUISITO OBRIGATÓRIO: Chave de API de Narração (DarkPlanner ou Google TTS)

As imagens (via Nano Banana integrado do Antigravity) e toda a animação/montagem de vídeo (`OpenCV` + `FFmpeg`) rodam **100% de graça na sua máquina**.

Porém, **para gerar a voz da narração (`scripts/audio.py`), você PRECISA configurar uma chave de API do DarkPlanner OU do Google TTS**:

### Como configurar sua chave de voz:

1. Na pasta raiz do repositório, copie o arquivo `.env.example` para `.env`:
   ```bash
   cp .env.example .env
   ```
2. Abra o arquivo `.env` e preencha **uma** das duas chaves abaixo:

   - **Opção A — DarkPlanner TTS API:**
     ```env
     DARKPLANNER_API_KEY="dpk_sua_chave_aqui"
     ```
     *(Acesso a +1.000 vozes documentais multilingues da ElevenLabs, como `"A Top Narrator VO PRO"` em inglês/português e `"Norbert"` em alemão, já com download nativo do `_palavra.srt`).*

   - **Opção B — Google Gemini TTS API (`gemini-2.5-flash-preview-tts`):**
     ```env
     GEMINI_API_KEY="AIzaSy_sua_chave_do_google_ai_studio"
     ```
     *(Chave gratuita criada em [aistudio.google.com/apikey](https://aistudio.google.com/apikey). Inclui vozes documentais multilingues como `Charon`, `Orus`, `Fenrir`, `Puck`, `Kore` e `Aoede`).*

3. Para listar as vozes disponíveis no seu terminal a qualquer momento:
   ```bash
   python scripts/audio.py --list-voices
   ```

---

## 🛠️ Instalação das Dependências Locais

Certifique-se de ter **Python 3.10+** e **FFmpeg** instalados no sistema, e instale as bibliotecas visuais:

```bash
pip install pillow numpy opencv-python-headless
```

---

## 🚀 Como Usar (Fluxo do Agente em 6 Etapas)

Basta abrir este repositório no **Antigravity** (ou Claude Code / Cursor) e pedir ao agente:

> *"Crie um vídeo estilo colagem da Vox sobre [SEU TEMA AQUI] em [IDIOMA]."*

O agente seguirá automaticamente o protocolo de 6 etapas definido no [`SKILL.md`](SKILL.md):

1. **Escolha da Voz & Roteiro (`beats.json`) — *Pergunta Obrigatória*:**
   - **Antes de gerar o áudio, o agente SEMPRE perguntará a você:**
     1. Qual provedor de voz você quer usar (**DarkPlanner** ou **Google TTS**)?
     2. **Qual voz (`voice_id` / nome da voz)** deve narrar o vídeo?
   - Em seguida, o agente monta o `beats.json` com cortes rápidos de **3.5s a 5s** para sua aprovação.
2. **Geração da Voz + Masterização Broadcast (`scripts/audio.py`):**
   - Gera os `.mp3` e os arquivos `_palavra.srt` de cada capítulo, aplica nivelamento dinâmico (`highpass + compressor + dynaudnorm + limiter`) e ajusta o tempo exato dos cortes.
3. **Engenharia de Prompt & Pôsteres de Colagem (`scripts/keyframes.py`):**
   - Compõe os prompts de 5 camadas (`scripts/styles.py`) e gera as gravuras 16:9 ou 9:16 com o **Nano Banana**.
4. **Decomposição & Animação dos Objetos da Gravura (`scripts/vox_animator.py`):**
   - Recorta os elementos internos das gravuras com `OpenCV`, reconstrói o fundo com `cv2.inpaint` e anima os objetos em *stop-motion* + efeitos procedurais 2D.
5. **Montagem Final + Legendas de Papel (`scripts/assemble.py`):**
   - Concatena todos os cortes animados, renderiza as legendas estilo recorte de papel sincronizadas ao `.srt` e exporta `out/<projeto>/final.mp4`.

---

## 📁 Estrutura do Repositório

```text
SKILL.md                    # Instruções completas do Agente (Regras de Voz, Cadência e Animação)
AGENTS.md                   # Ponto de entrada para agentes compatíveis (Antigravity, Codex, Cursor)
.env.example                # Modelo de configuração da chave DARKPLANNER_API_KEY ou GEMINI_API_KEY
scripts/
  audio.py                  # Conector Dual TTS (DarkPlanner API + Google Gemini TTS + Broadcast EQ)
  keyframes.py              # Gerador de prompts de colagem Vox para Nano Banana
  vox_animator.py           # Motor OpenCV + Pillow + FFmpeg que anima os objetos dentro das gravuras
  assemble.py               # Montador final FFmpeg com legendas dinâmicas sincronizadas ao .srt
  text_overlay.py           # Renderizador de legendas em estilo recorte de papel ("paper" / "white")
  styles.py                 # 9 presets de temas visuais (swiss-modern, american-retro, punk-zine, etc.)
  motion.py                 # Motor de keyframes por camadas (fly_in, slap, drop, bounce)
  kenburns.py               # Fallback rápido de câmera via FFmpeg
references/
  prompt-guide.md           # Guia completo da camada visual (LOOK layer)
  beat-layer.md             # 14 arcos narrativos e regras de cadência (cortes de 3–5s)
  local-engine.md           # Documentação do motor local de recorte e inpainting
examples/                   # Exemplos prontos de beats.json
```

---

## 📄 Licença

Distribuído sob a licença [MIT](LICENSE). Adaptado e expandido para a comunidade **Dark Society**.
