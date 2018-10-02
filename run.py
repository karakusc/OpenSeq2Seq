# Copyright (c) 2017 NVIDIA Corporation
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import sys
import tensorflow as tf
from open_seq2seq.utils.utils import deco_print, get_base_config, check_logdir,\
                                     create_logdir, create_model, check_base_model_logdir
from open_seq2seq.utils import train, infer, evaluate

from mpi4py import MPI
def get_subcluster():
  comm = MPI.COMM_WORLD
  local_comm = comm.Split_type(MPI.COMM_TYPE_SHARED, comm.Get_rank())
  local_size = local_comm.Get_size()

  group_size = local_size//2
  subcluster_left = (comm.rank // group_size) * group_size

  subcluster_right = subcluster_left + group_size
  return [i for i in range(subcluster_left, subcluster_right)]

def main():
  # Parse args and create config
  args, base_config, base_model, config_module = get_base_config(sys.argv[1:])

  if args.mode == "interactive_infer":
    raise ValueError(
        "Interactive infer is meant to be run from an IPython",
        "notebook not from run.py."
    )

#   restore_best_checkpoint = base_config.get('restore_best_checkpoint', False)
#   # Check logdir and create it if necessary
#   checkpoint = check_logdir(args, base_config, restore_best_checkpoint)
  
  load_model = base_config.get('load_model', None)
  restore_best_checkpoint = base_config.get('restore_best_checkpoint', False)
  base_ckpt_dir = check_base_model_logdir(load_model, restore_best_checkpoint)
  base_config['load_model'] = base_ckpt_dir

  # Check logdir and create it if necessary
  checkpoint = check_logdir(args, base_config, restore_best_checkpoint)

  # Initilize Horovod
  if base_config['use_horovod']:
    import horovod.tensorflow as hvd
    #hvd.init()
    hvd.init(get_subcluster(), keep_global=True)
    if hvd.rank() == 0:
      deco_print("Using horovod")
  else:
    hvd = None



  if args.enable_logs:
    if hvd is None or hvd.rank() == 0:
      old_stdout, old_stderr, stdout_log, stderr_log = create_logdir(
          args,
          base_config
      )
    base_config['logdir'] = os.path.join(base_config['logdir'], 'logs')

  if args.mode == 'train' or args.mode == 'train_eval' or args.benchmark:
    if hvd is None or hvd.rank() == 0:
      if checkpoint is None or args.benchmark:
        if base_ckpt_dir:
          deco_print("Starting training from the base model")
        else:
          deco_print("Starting training from scratch")
      else:
        deco_print(
            "Restored checkpoint from {}. Resuming training".format(checkpoint),
        )
  elif args.mode == 'eval' or args.mode == 'infer':
    if hvd is None or hvd.rank() == 0:
      deco_print("Loading model from {}".format(checkpoint))

  # Create model and train/eval/infer
  with tf.Graph().as_default():
    model = create_model(args, base_config, config_module, base_model, hvd, restore_best_checkpoint)
    if args.mode == "train_eval":
      train(model[0], model[1], debug_port=args.debug_port)
    elif args.mode == "train":
      train(model, None, debug_port=args.debug_port)
    elif args.mode == "eval":
      evaluate(model, checkpoint)
    elif args.mode == "infer":
      infer(model, checkpoint, args.infer_output_file, args.use_trt)

  if args.enable_logs and (hvd is None or hvd.rank() == 0):
    sys.stdout = old_stdout
    sys.stderr = old_stderr
    stdout_log.close()
    stderr_log.close()


if __name__ == '__main__':
  main()
