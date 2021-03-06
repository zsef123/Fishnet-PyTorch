import torch
import torch.nn as nn

from residual import ResBlock, _bn_relu_conv
from residual import DownStage, UpStage, TransferBlock


class FishTail(nn.Module):
    """
    Construct FishTail module.
    Each instances corresponds to each stages.
    
    Args:
        in_c : Number of channels in the input image
        out_c : Number of channels in the output image
        num_blk : Number of Residual Blocks

    Forwarding Path:
        input image - (DownStage) - output
    """
    def __init__(self, in_c, out_c, num_blk):
        super().__init__()
        self.layer = DownStage(in_c, out_c, num_blk)

    def forward(self, x):
        return self.layer(x)


class Bridge(nn.Module):
    """
    Construct Bridge module.
    This module bridges the last FishTail stage and first FishBody stage.
    
    Args:
        ch : Number of channels in the input and output image
        num_blk : Number of Residual Blocks

    Forwarding Path:
                        r                        (SEBlock)                           ㄱ 
        input image - (stem) - (ResBlock with Shortcut) - (ResBlock) * num_blk - (mul & sum) - output
    """         
    def __init__(self, ch, num_blk):
        super().__init__()

        self.stem = nn.Sequential(
            nn.BatchNorm2d(ch),
            nn.ReLU(True),
            nn.Conv2d(ch, ch//2, kernel_size=1, bias=False),
            nn.BatchNorm2d(ch//2),
            nn.ReLU(True),
            nn.Conv2d(ch//2, ch*2, kernel_size=1, bias=True)
        )

        shortcut = _bn_relu_conv(ch*2, ch, kernel_size=1, bias=False)
        self.layers = nn.Sequential(
            ResBlock(ch*2, ch, shortcut=shortcut),
            *[ResBlock(ch, ch) for _ in range(1, num_blk)],
        )

        # https://github.com/kevin-ssy/FishNet/blob/master/models/fishnet.py#L45
        self.se_block = nn.Sequential(
            nn.BatchNorm2d(ch*2),
            nn.ReLU(True),
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(ch*2, ch//16, kernel_size=1),
            nn.ReLU(True),
            nn.Conv2d(ch//16, ch, kernel_size=1),
            nn.Sigmoid()
        )

    def forward(self, x):
        x = self.stem(x)
        att = self.se_block(x)
        out = self.layers(x)
        return (out * att) + att

  
class FishBody(nn.Module):
    r"""Construct FishBody module.
    Each instances corresponds to each stages.
    
    
    Args:
        in_c : Number of channels in the input image
        out_c : Number of channels in the output image
        num_blk : Number of Residual Blocks
        trans_in_c : Number of channels in the transferred image
        num_trans : Number of Transfer Blocks
        dilation : Dilation rate of Conv in UpRefinementBlock
        
    Forwarding Path:
        input image - (UpStage)       ㄱ
        trans image - (transfer) --(concat)-- output
    """
    def __init__(self, in_c, out_c, num_blk,
                 trans_in_c, num_trans,
                 dilation=1):
        super().__init__()
        self.layer = UpStage(in_c, out_c, num_blk, dilation=dilation)
        self.transfer = TransferBlock(trans_in_c, num_trans)

    def forward(self, x, trans_x):
        x = self.layer(x)
        trans_x = self.transfer(trans_x)
        return torch.cat([x, trans_x], dim=1)

class FishHead(nn.Module):
    r"""Construct FishHead module.
    Each instances corresponds to each stages.

    Different with Offical Code : we used shortcut layer in this Module. (shortcut layer is used according to the original paper)
    
    Args:
        in_c : Number of channels in the input image
        out_c : Number of channels in the output image
        num_blk : Number of Residual Blocks
        trans_in_c : Number of channels in the transferred image
        num_trans : Number of Transfer Blocks
        
    Forwarding Path:
        input image - (ResBlock) * num_blk - pool ㄱ
        trans image - (transfer)             --(concat)-- output
    """
    def __init__(self, in_c, out_c, num_blk,
                 trans_in_c, num_trans):
        super().__init__()

        self.layer = nn.Sequential(
            ResBlock(in_c, out_c),
            *[ResBlock(out_c, out_c) for _ in range(1, num_blk)],
            nn.MaxPool2d(2, stride=2)
        )
        self.transfer = TransferBlock(trans_in_c, num_trans)

    def forward(self, x, trans_x):
        x = self.layer(x)
        trans_x = self.transfer(trans_x)
        return torch.cat([x, trans_x], dim=1)

