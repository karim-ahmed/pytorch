import functools
import torch
import torch.distributed as dist


from enum import Enum


TORCH_HALF_MIN = torch.finfo(torch.float16).min
TORCH_HALF_MAX = torch.finfo(torch.float16).max

class DQuantType(Enum):
    FP16 = "fp16"

    def __str__(self) -> str:
        return self.value


def _fp32_to_fp16_with_clamp(tensor: torch.Tensor) -> torch.Tensor:
    return torch.clamp(tensor, TORCH_HALF_MIN, TORCH_HALF_MAX).half()

def _quantize_tensor(tensor, qtype):
    if not isinstance(tensor, torch.Tensor):
        raise RuntimeError(
            f"_quantize_tensor expecting torch.Tensor as input but found {type(tensor)}"
        )
    if (qtype == DQuantType.FP16):
        return _fp32_to_fp16_with_clamp(tensor)
    else:
        raise RuntimeError(
            f'Quantization type {qtype} is not supported'
        )

def _quantize_tensor_list(tensor_list, qtype):
    if not isinstance(tensor_list, list) or not all(
        isinstance(p, torch.Tensor) for p in tensor_list
    ):
        raise RuntimeError(
            f"_quantize_tensor_list expecting list of torch.Tensor as input but found {type(tensor_list)}"
        )
    if (qtype == DQuantType.FP16):
        quantized_tensor_list = [_quantize_tensor(t, qtype) for t in tensor_list]
        return quantized_tensor_list
    else:
        raise RuntimeError(
            f'Quantization type {qtype} is not supported'
        )

def _dequantize_tensor(tensor, qtype, quant_loss=None):
    if not isinstance(tensor, torch.Tensor):
        raise RuntimeError(
            f"_dequantize_tensor expecting torch.Tensor as input but found {type(tensor)}"
        )
    if (qtype == DQuantType.FP16):
        if tensor.dtype != torch.float16:
            raise RuntimeError(
                f"tensor dtype is {tensor.dtype} while expected to be FP16."
            )
        elif tensor.dtype == torch.float16 and quant_loss is None:
            return tensor.float()
        else:
            return tensor.float() / quant_loss
    else:
        raise RuntimeError(
            f'Quantization type {qtype} is not supported'
        )


def _dequantize_tensor_list(tensor_list, qtype, quant_loss=None):
    if not isinstance(tensor_list, list) or not all(
        isinstance(p, torch.Tensor) for p in tensor_list
    ):
        raise RuntimeError(
            f"_dequantize_tensor_list expecting list of torch.Tensor as input but found {type(tensor_list)}"
        )
    elif (qtype == DQuantType.FP16):
        dequantized_tensor_list = [_dequantize_tensor(t, qtype) for t in tensor_list]
        return dequantized_tensor_list
    else:
        raise RuntimeError(
            f'Quantization type {qtype} is not supported'
        )


def auto_quantize(func, qtype, quant_loss=None):
    """
    This is a prototype API that automatically quantize the input tensors, choose the precision types, and
    pass other necessary arguments and then dequantizes the output.
    Currently it only supports:
        . FP16 quantization method
        . all_gather, all_to_all collective ops
    Args:
        func (callable): A function representing collective operations.
        qtype (QuantType): Quantization method
        quant_loss (float, optional): This can be used to improve accuracy in the dequantization.
    Returns:
        (callable): the same collective as func but enables automatic quantization/dequantization.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        group = kwargs.get('group', None)
        async_op = kwargs.get('async_op', False)
        if (async_op is True):
            raise RuntimeError(
                'The async_op=True mode is not supported yet.'
            )
        if (func == dist.all_gather):
            tensors = args[0]
            input_tensors = _quantize_tensor(args[1], qtype)
            out_tensors = _quantize_tensor_list(tensors, qtype)
            dist.all_gather(out_tensors, input_tensors, group=group, async_op=async_op)
            for i, t in enumerate(_dequantize_tensor_list(out_tensors, qtype, quant_loss=quant_loss)):
                tensors[i] = t

        elif (func == dist.all_to_all):
            tensors = args[0]
            input_tensors = _quantize_tensor_list(args[1], qtype)
            out_tensors = _quantize_tensor_list(tensors, qtype)
            dist.all_to_all(out_tensors, input_tensors, group=group, async_op=async_op)
            for i, t in enumerate(_dequantize_tensor_list(out_tensors, qtype, quant_loss=quant_loss)):
                tensors[i] = t

        else:
            raise RuntimeError(
                f"The collective op {func} is not supported yet"
            )

    return wrapper
