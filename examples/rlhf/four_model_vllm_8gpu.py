import torch

MAX_PROMPT_LEN = 1024
MAX_ANSWER_LEN = 1024
MAX_PRETRAIN_LEN = 8192

PROMPT_BATCH_SIZE = 256
PRETRAIN_BATCH_SIZE = 32

GENERATE_MICRO_BATCH_SIZE = 16
AC_INFER_MICRO_BATCH_SIZE = 8
REF_INFER_MICRO_BATCH_SIZE = 8
TRAIN_MICRO_BATCH_SIZE = 2

ZERO_STAGE = 3
ACTOR_DP_SIZE = 2
CRITIC_DP_SIZE = 2
ACTOR_GRADIENT_ACC_STEP = (PROMPT_BATCH_SIZE + PRETRAIN_BATCH_SIZE
                           ) // ACTOR_DP_SIZE // TRAIN_MICRO_BATCH_SIZE
CRITIC_GRADIENT_ACC_STEP = PROMPT_BATCH_SIZE // CRITIC_DP_SIZE // TRAIN_MICRO_BATCH_SIZE

MODEL_DTYPE = 'auto'

tokenizer_config = dict(
    pad_token_id=0,
    eos_token_id=92542,
    padding_side='left',
)

rollout_config = dict(
    actor_micro_bs=GENERATE_MICRO_BATCH_SIZE,
    reward_micro_bs=GENERATE_MICRO_BATCH_SIZE,
    max_new_tokens=MAX_ANSWER_LEN,
    write_to_file=True,
    generate_kwargs={
        'do_sample': True,
        'temperature': 1.0,
        'top_k': 0,
        'top_p': 0.9,
        'min_new_tokens': 1,
        'num_beams': 1,
        'early_stopping': True,
        'eos_token_id': 92542,
        'pad_token_id': 0,
    },
)

repeater_config = dict(
    actor_micro_bs=AC_INFER_MICRO_BATCH_SIZE,
    critic_micro_bs=AC_INFER_MICRO_BATCH_SIZE,
    ref_micro_bs=REF_INFER_MICRO_BATCH_SIZE,
    kl_coeff=0.01,
    gamma=1.0,
    gae_lambda=0.99,
    clip_reward_min=-5,
    clip_reward_max=5,
    answer_end_id=92542,
    norm_rewards=True,
)

train_config = dict(
    actor_micro_bs=TRAIN_MICRO_BATCH_SIZE,
    critic_micro_bs=TRAIN_MICRO_BATCH_SIZE,
    ppo_loss_weight=1.0,
    pretrain_loss_weight=0.5,
    pretrain_step=20,
    save_interval=40,
)

model_configs = dict(
    actor=dict(
        model_path='internlm/internlm2-chat-1_8b-sft',
        model_type='actor',
        trainer_config=dict(
            torch_dtype=MODEL_DTYPE,
            trainer_type='huggingface',
            use_flash_attn=True,
            gradient_checkpointing=False,
            train_kwargs=dict(
                micro_bsz=1,
                lr=1e-6,
                total_steps=1e9,
                lr_decay_rate=1,
                loss_type='per_seq',
            ),
            parallel=dict(
                data=dict(size=ACTOR_DP_SIZE, mode='deepspeed'),
                tensor=dict(size=1, mode='1d'),
                pipeline=dict(size=1, interleaved_overlap=False),
                sequence=False,
            ),
            deepspeed_config={
                'zero_optimization': {
                    'stage': ZERO_STAGE,
                    'offload_param': {
                        'device': 'none'
                    },
                    'reduce_bucket_size': 'auto',
                    'zero_hpz_partition_size': 1,
                    'zero_quantized_weights': False,
                    'zero_quantized_gradients': False,
                    'stage3_gather_16bit_weights_on_model_save': True,
                },
                'bf16': {
                    'enabled': True
                },
                'gradient_clipping': 1.0,
                'prescale_gradients': False,
                'wall_clock_breakdown': False,
                'data_types': {
                    'grad_accum_dtype': 'fp32'
                },
                'train_micro_batch_size_per_gpu': TRAIN_MICRO_BATCH_SIZE,
                'gradient_accumulation_steps': ACTOR_GRADIENT_ACC_STEP,
                'train_batch_size': PROMPT_BATCH_SIZE + PRETRAIN_BATCH_SIZE,
            },
        ),
        generator_config=dict(
            shared_with_trainer=False,
            generator_type='vllm',
            parallel=dict(
                data=dict(size=1, mode='ddp'),
                tensor=dict(size=2, mode='1d'),
                pipeline=dict(size=1, interleaved_overlap=False),
                sequence=False,
            ),
        ),
    ),
    critic=dict(
        model_path=None,
        model_type='critic',
        trainer_config=dict(
            torch_dtype=MODEL_DTYPE,
            trainer_type='huggingface',
            use_flash_attn=True,
            gradient_checkpointing=False,
            train_kwargs=dict(
                micro_bsz=1,
                lr=5e-6,
                total_steps=1e9,
                lr_decay_rate=1,
                loss_type='per_seq',
            ),
            parallel=dict(
                data=dict(size=CRITIC_DP_SIZE, mode='deepspeed'),
                tensor=dict(size=1, mode='1d'),
                pipeline=dict(size=1, interleaved_overlap=False),
                sequence=False,
            ),
            deepspeed_config={
                'zero_optimization': {
                    'stage': ZERO_STAGE,
                    'offload_param': {
                        'device': 'none'
                    },
                    'reduce_bucket_size': 'auto',
                    'zero_hpz_partition_size': 1,
                    'zero_quantized_weights': False,
                    'zero_quantized_gradients': False
                },
                'bf16': {
                    'enabled': True
                },
                'gradient_clipping': 1.0,
                'prescale_gradients': False,
                'wall_clock_breakdown': False,
                'data_types': {
                    'grad_accum_dtype': 'fp32'
                },
                'train_micro_batch_size_per_gpu': TRAIN_MICRO_BATCH_SIZE,
                'gradient_accumulation_steps': CRITIC_GRADIENT_ACC_STEP,
                'train_batch_size': PROMPT_BATCH_SIZE,
            },
        ),
    ),
    reference=dict(
        model_path='internlm/internlm2-chat-1_8b-sft',
        model_type='reference',
        trainer_config=dict(
            torch_dtype=MODEL_DTYPE,
            trainer_type='huggingface',
            use_flash_attn=True,
            parallel=dict(
                data=dict(size=1, mode='ddp'),
                tensor=dict(size=1, mode='1d'),
                pipeline=dict(size=1, interleaved_overlap=False),
                sequence=False,
            ),
        ),
    ),
    reward=dict(
        model_path=None,
        model_type='reward',
        trainer_config=dict(
            torch_dtype=MODEL_DTYPE,
            trainer_type='huggingface',
            use_flash_attn=True,
            parallel=dict(
                data=dict(size=1, mode='ddp'),
                tensor=dict(size=1, mode='1d'),
                pipeline=dict(size=1, interleaved_overlap=False),
                sequence=False,
            ),
        ),
    ),
)

dataset_config = {
    'prompt_samples_each_epoch':
    PROMPT_BATCH_SIZE,
    'max_prompt_len':
    MAX_PROMPT_LEN,
    'pretrain_samples_each_epoch':
    PRETRAIN_BATCH_SIZE,
    'max_pretrain_len':
    MAX_PRETRAIN_LEN,
    'random_seed':
    1024,
    # "sample_strategy": "in_data",
    # "ratio_within_datasets": False,
    'prompt_datasets': [
        'Anthropic/hh-rlhf/helpful-base::1.0',
        'Anthropic/hh-rlhf/harmless-base::0.5',
    ],
    'pretrain_datasets': [
        'Anthropic/hh-rlhf/helpful-base::1.0',
    ],
}
