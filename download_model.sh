#!/bin/bash
# Download Qwen-Image-2512 model files

BASE_URL="https://huggingface.co/Qwen/Qwen-Image-2512/resolve/main"
MODEL_DIR="/data/models/Qwen-Image-2512"

mkdir -p "$MODEL_DIR"/{scheduler,text_encoder,tokenizer,transformer,vae}

cd "$MODEL_DIR"

echo "Downloading Qwen-Image-2512..."

# Root files
wget -q -nc "$BASE_URL/model_index.json"

# Scheduler
echo "Downloading scheduler..."
wget -q -nc "$BASE_URL/scheduler/scheduler_config.json" -P scheduler/

# Tokenizer
echo "Downloading tokenizer..."
wget -q -nc "$BASE_URL/tokenizer/tokenizer_config.json" -P tokenizer/
wget -q -nc "$BASE_URL/tokenizer/vocab.json" -P tokenizer/
wget -q -nc "$BASE_URL/tokenizer/merges.txt" -P tokenizer/
wget -q -nc "$BASE_URL/tokenizer/special_tokens_map.json" -P tokenizer/

# Text encoder (4 shards ~8GB)
echo "Downloading text_encoder..."
wget -q -nc "$BASE_URL/text_encoder/config.json" -P text_encoder/
for i in $(seq -w 1 4); do
  echo "  text_encoder shard $i/4..."
  wget -q --show-progress -nc "$BASE_URL/text_encoder/model-0000${i}-of-00004.safetensors" -P text_encoder/
done
wget -q -nc "$BASE_URL/text_encoder/model.safetensors.index.json" -P text_encoder/

# VAE (~300MB)
echo "Downloading vae..."
wget -q -nc "$BASE_URL/vae/config.json" -P vae/
wget -q --show-progress -nc "$BASE_URL/vae/diffusion_pytorch_model.safetensors" -P vae/

# Transformer (9 shards ~35GB)
echo "Downloading transformer (largest component)..."
wget -q -nc "$BASE_URL/transformer/config.json" -P transformer/
wget -q -nc "$BASE_URL/transformer/diffusion_pytorch_model.safetensors.index.json" -P transformer/
for i in $(seq -w 1 9); do
  echo "  transformer shard $i/9..."
  wget -q --show-progress -nc "$BASE_URL/transformer/diffusion_pytorch_model-0000${i}-of-00009.safetensors" -P transformer/
done

echo "Download complete!"
du -sh "$MODEL_DIR"
