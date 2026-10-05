#!/usr/bin/env bash
# Copiloto de Reunião — preparação do Mac
# O Mac não deixa programas ouvirem o áudio do sistema sem um "cabo virtual". Usamos o BlackHole (grátis, open source).
set -e

echo "== Copiloto de Reunião: preparando o Mac =="

if ! command -v brew >/dev/null 2>&1; then
  echo "Precisa do Homebrew. Instale com:"
  echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  exit 1
fi

command -v python3 >/dev/null 2>&1 || brew install python@3.12
brew list portaudio >/dev/null 2>&1 || brew install portaudio

if ! system_profiler SPAudioDataType 2>/dev/null | grep -qi blackhole; then
  echo "Instalando o BlackHole 2ch (vai pedir sua senha do Mac)…"
  brew install --cask blackhole-2ch
fi

cat <<'TXT'

== Último passo (1 minuto, só na primeira vez) ==
1. Abra o app "Configuração de Áudio MIDI" (Audio MIDI Setup): Cmd+Espaço e digite "MIDI".
2. Clique no "+" no canto de baixo e escolha "Criar Dispositivo de Saída Múltipla" (Multi-Output Device).
3. Marque os seus fones/alto-falantes E o "BlackHole 2ch". Ligue "Correção de deriva" no BlackHole.
4. Em Ajustes do Sistema > Som > Saída, escolha esse "Dispositivo de Saída Múltipla".
   (Volume: ajuste no próprio fone/alto-falante; o Multi-Output não tem controle de volume.)
5. No Meet/Zoom, deixe a saída de áudio como "Padrão do sistema".

Pronto: você continua ouvindo normalmente e o copiloto também ouve o cliente.
Teste com: /reuniao-teste
TXT
