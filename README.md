# 🎬 Vox Collage — Dark Society Edition (Exclusivo para Google Antigravity)

**Transforme qualquer tema — ou um roteiro com áudio já pronto — em um documentário estilo Colagem de Papel da Vox (*Vox-Style Paper-Collage Explainer*), 100% automatizado dentro do Google Antigravity + OpenCV + FFmpeg.**

![Platform: Google Antigravity](https://img.shields.io/badge/Platform-Google%20Antigravity-4285F4.svg) ![Engine: Local OpenCV + FFmpeg](https://img.shields.io/badge/Engine-OpenCV%20%2B%20FFmpeg-d92b2b.svg) ![Audio: DarkPlanner | Google TTS | Áudio Próprio](https://img.shields.io/badge/Audio-DarkPlanner%20%7C%20Google%20TTS%20%7C%20MP3%20Pr%C3%B3prio-0e8a5f.svg)

---

## 🧩 O que é este repositório?

Este projeto foi construído **especificamente para rodar no Google Antigravity**, aproveitando o gerador **Nano Banana integrado nativamente ao Antigravity (`image-generator`)** para produzir vídeos *faceless* de alta retenção no estilo **Editorial Motion Collage** (popularizado pela **Vox** e **Johnny Harris**):

- **Gravuras de Colagem Física (via Nano Banana nativo do Antigravity):** Pôsteres com textura de papel rasgado à mão, recortes de jornal em *halftone*, fita crepe, alfinetes, barbante vermelho e manchetes tipográficas — sem gastar nada com APIs externas de imagem.
- **Animação Real dos Objetos da Gravura (`scripts/vox_animator.py`):** Em vez de apenas dar zoom estático na foto inteira, o motor em **OpenCV (`cv2.inpaint`) + NumPy + Pillow + FFmpeg** recorta os objetos de dentro da própria gravura, reconstrói o fundo de papel/quadriculado por trás deles e anima cada peça em **stop-motion (10 fps)** com física elástica (`ease_out_back`), ponteiros girando, setas de gráficos crescendo, rotas pulsando no mapa e *camera shake*.
- **Cadência Dinâmica de Retenção:** Cortes rápidos a cada **3.5 a 5 segundos**, intercalando planos gerais (*Wide*) com cortes de detalhe (*Cut-ins*) sincronizados à fala.
- **Legendas Nativas em Recorte de Papel (`scripts/text_overlay.py`):** Legendas sincronizadas ao `.srt` com borda colorida extraída automaticamente da paleta de cada gravura.

---

## 🎙️ 2 FORMAS DE USAR O ÁUDIO / NARRAÇÃO

Você pode produzir seus vídeos de **duas maneiras**:

### MODO 1 — Gerar a Voz Automaticamente (DarkPlanner API ou Google TTS)
Se você quiser que o próprio agente crie o roteiro e gere a narração automaticamente, adicione uma chave de API do **DarkPlanner** OU do **Google TTS** no arquivo `.env`:

1. Na pasta raiz do repositório, copie o arquivo `.env.example` para `.env`:
   ```bash
   cp .env.example .env
   ```
2. Abra o arquivo `.env` e preencha **uma** das duas opções:
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

> 💡 **Pergunta Obrigatória de Voz:** Sempre que você pedir um roteiro novo, o agente do Antigravity **perguntará automaticamente qual provedor (DarkPlanner ou Google TTS) e qual voz você quer usar** antes de gerar o áudio! Para listar as vozes pelo terminal:
> ```bash
> python scripts/audio.py --list-voices
> ```

---

### MODO 2 — Mandar Roteiro Pronto + Áudio Pronto (Sem precisar de API de voz!)
Se você já gerou a narração por fora (no seu próprio gerador, ElevenLabs, CapCut, etc.), **você não precisa configurar nenhuma chave de API**!

Basta enviar no chat do Antigravity:
1. O seu **roteiro pronto**; e
2. O caminho do seu **arquivo de áudio `.mp3` ou `.wav`** (ou colocá-lo em `out/<projeto>/audio/master.mp3`).

O script `scripts/audio.py --from-audio seu_audio.mp3` fará tudo sozinho:
- Fatia e sincroniza o seu áudio automaticamente entre os capítulos (*beats*) e cenas (*shots* de 3.5s a 5s);
- Aplica a **Masterização Broadcast** (`highpass + compressor + dynaudnorm + limiter`);
- Gera os arquivos `_palavra.srt` para as legendas em papel recortado ficarem 100% sincronizadas!

---

## 🛠️ Instalação das Dependências Locais

1. Abra o repositório no **Google Antigravity**.
2. Certifique-se de ter **Python 3.10+** e **FFmpeg** instalados no sistema, e instale as bibliotecas visuais:

```bash
pip install pillow numpy opencv-python-headless
```

---

## 🚀 Como Usar no Google Antigravity (Passo a Passo)

No chat do **Antigravity**, você pode pedir de duas formas:

- **A partir de um tema (Modo 1):**
  > *"Crie um vídeo estilo colagem da Vox sobre [SEU TEMA AQUI] em [IDIOMA]."*
  *(O agente vai te perguntar qual voz do DarkPlanner ou Google TTS você quer usar e montar o roteiro).*

- **A partir de um roteiro + áudio pronto (Modo 2):**
  > *"Quero criar um vídeo estilo Vox com este roteiro aqui e usando o áudio pronto que está em `C:\caminho\meu_audio.mp3`."*

### O que o Antigravity executa automaticamente:
1. **Beat Map (`beats.json`):** Divide o roteiro em capítulos e takes rápidos de **3.5s a 5s** (intercalando *Wide* com manchete e *Cut-ins* de detalhe).
2. **Áudio & Sincronização (`scripts/audio.py`):** Gera a voz via DarkPlanner/Google TTS (ou fatia o seu `.mp3` pronto), nivela o áudio e gera os `.srt`.
3. **Pôsteres de Colagem (`scripts/keyframes.py` + Nano Banana do Antigravity):** Gera todas as gravuras de colagem de papel rasgado direto pelo subagente nativo `image-generator`.
4. **Animação dos Objetos da Gravura (`scripts/vox_animator.py`):** Recorta os elementos internos das gravuras com `OpenCV`, reconstrói o fundo com `cv2.inpaint` e anima os objetos em *stop-motion* + efeitos procedurais 2D.
5. **Montagem Final + Legendas de Papel (`scripts/assemble.py`):** Concatena todos os cortes animados, queima as legendas estilo recorte de papel sincronizadas ao `.srt` e exporta `out/<projeto>/final.mp4`.

---

## 📁 Estrutura do Repositório

```text
SKILL.md                    # Instruções completas do Agente no Google Antigravity
AGENTS.md                   # Regras obrigatórias de seleção de voz, áudio pronto e cadência
.env.example                # Modelo de configuração da chave DARKPLANNER_API_KEY ou GEMINI_API_KEY
scripts/
  audio.py                  # Motor Triplo de Áudio (DarkPlanner API | Google Gemini TTS | Áudio Pronto --from-audio)
  keyframes.py              # Gerador de prompts de colagem Vox para o Nano Banana do Antigravity
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
examples/                   # Exemplos prontos de beats.json (incluindo singapore-vs-malaysia)
```

---

## 📄 Licença

Distribuído sob a licença [MIT](LICENSE). Desenvolvido para a comunidade **Dark Society**.
