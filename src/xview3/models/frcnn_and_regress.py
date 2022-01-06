import types
import torch
import torchvision
import torch.nn as nn
import torch.nn.functional as F
from torchvision.ops import boxes as box_ops
from torchvision.models.detection.anchor_utils import AnchorGenerator
from torchvision.models.detection._utils import BoxCoder
from torchvision.models.detection.faster_rcnn import FasterRCNN
from torchvision.models.detection.backbone_utils import resnet_fpn_backbone


class FasterRCNNRegress(torch.nn.Module):
    """
    Baseline model class for xView3 reference implementation.
    Wraps torchvision faster-rcnn, updates initial layer to handle
    man arbitrary number of input channels.
    """

    def __init__(self, num_classes, num_channels, device, config, image_size=800):
        super(FasterRCNNRegress, self).__init__()

        image_mean = [float(a) for a in config.get("ImageMean").strip().split(",")]
        image_std = [float(a) for a in config.get("ImageStd").strip().split(",")]
        backbone = config.get("Backbone", fallback="resnet50")
        pretrained = config.getboolean("Pretrained", fallback=True)
        pretrained_backbone = config.getboolean("Pretrained-Backbone", fallback=True)
        trainable_backbone_layers = config.getint("Trainable-Backbone-Layers", fallback=5)

        # Load in a backbone, with capability to be pretrained on COCO
        if backbone == 'resnet50':
            self.faster_rcnn = torchvision.models.detection.fasterrcnn_resnet50_fpn(
                pretrained=pretrained,
                image_mean=image_mean,
                image_std=image_std,
                min_size=image_size,
                max_size=image_size,
                pretrained_backbone=pretrained_backbone,
                trainable_backbone_layers=trainable_backbone_layers
            )
        elif backbone == 'resnet101':
            self.faster_rcnn = fasterrcnn_resnet101_fpn(
                pretrained=pretrained,
                progress=True,
                num_classes=num_classes,
                pretrained_backbone=pretrained_backbone,
                trainable_backbone_layers=trainable_backbone_layers,
                image_mean=image_mean,
                image_std=image_std,
                min_size=image_size,
                max_size=image_size
            )
        elif backbone == 'mobilenet-320':
            self.faster_rcnn = torchvision.models.detection.fasterrcnn_mobilenet_v3_large_320_fpn(
                pretrained=pretrained,
                image_mean=image_mean,
                image_std=image_std,
                min_size=image_size,
                max_size=image_size,
                pretrained_backbone=pretrained_backbone,
                trainable_backbone_layers=trainable_backbone_layers
            )
        else:
            raise Exception("Please pass in a valid backbone argument: resnet50, resnet101, mobilenet-320")

        # replace the anchor generator with custom sizes and aspect ratios
        # TODO: this number of sizes and ratios is hardcoded here because FRCNN's desired format is odd, clean up
        s = [int(s) for s in config.get("AnchorSizes").strip().split(",")]
        r = [float(r) for r in config.get("AnchorRatios").strip().split(",")]
        sizes = ((s[0],), (s[1],), (s[2],), (s[3],), (s[4],))
        ratios = ((r[0], r[1], r[2]),) * len(sizes)
        anchor_generator = AnchorGenerator(sizes=sizes, aspect_ratios=ratios)
        self.faster_rcnn.rpn.anchor_generator = anchor_generator

        # replace the classifier with a new one for user-defined num_classes
        in_features = self.faster_rcnn.roi_heads.box_predictor.cls_score.in_features
        self.faster_rcnn.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)

        self.faster_rcnn.roi_heads.forward = types.MethodType(roi_heads_forward, self.faster_rcnn.roi_heads)
        self.faster_rcnn.roi_heads.select_training_samples = types.MethodType(select_training_samples, self.faster_rcnn.roi_heads)

        print(f"Using {num_channels} channels for input layer...")
        self.num_channels = num_channels
        if num_channels > 3:
            # Adjusting initial layer to handle arbitrary number of inputchannels
            self.faster_rcnn.backbone.body.conv1 = torch.nn.Conv2d(
                num_channels,
                self.faster_rcnn.backbone.body.conv1.out_channels,
                kernel_size=7,
                stride=2,
                padding=3,
                bias=False,
            )

    def forward(self, *input, **kwargs):
        if self.num_channels < 3:
            # Copy the first channel until we have three channel input.
            input = list(input)
            new_imgs = []
            for img in input[0]:
                l = [img]
                for _ in range(3-self.num_channels):
                    l.append(img[0:1])
                new_imgs.append(torch.cat(l, dim=0))
            input[0] = new_imgs
            input = tuple(input)

        out = self.faster_rcnn.forward(*input, **kwargs)
        return out


def fasterrcnn_resnet101_fpn(pretrained=True, progress=True,
                            num_classes=3, pretrained_backbone=True,
                             trainable_backbone_layers=3, **kwargs):
    assert trainable_backbone_layers <= 5 and trainable_backbone_layers >= 0
    # dont freeze any layers if pretrained model or backbone is not used
    if not (pretrained or pretrained_backbone):
        trainable_backbone_layers = 3
    if pretrained:
        # no need to download the backbone if pretrained is set
        pretrained_backbone = False
    backbone = resnet_fpn_backbone('resnet101', pretrained_backbone)
    model = FasterRCNN(backbone, num_classes, **kwargs)
    return model


### NOTE: copying torchvision frcnn code over so we can alter it to incorporate vesseln length predictions
class FastRCNNPredictor(nn.Module):
    """
    Standard classification + bounding box regression + vessel length regression layers
    for Fast R-CNN.

    Args:
        in_channels (int): number of input channels
        num_classes (int): number of output classes (including background)
    """

    def __init__(self, in_channels, num_classes):
        super(FastRCNNPredictor, self).__init__()
        self.cls_score = nn.Linear(in_channels, num_classes)
        self.bbox_pred = nn.Linear(in_channels, num_classes * 4)
        self.vessel_len = nn.Linear(in_channels, 1)

    def forward(self, x):
        if x.dim() == 4:
            assert list(x.shape[2:]) == [1, 1]
        x = x.flatten(start_dim=1)
        scores = self.cls_score(x)
        bbox_deltas = self.bbox_pred(x)
        vessel_lens = self.vessel_len(x)

        return scores, bbox_deltas, vessel_lens


def roi_heads_forward(
    self,
    features,  # type: Dict[str, Tensor]
    proposals,  # type: List[Tensor]
    image_shapes,  # type: List[Tuple[int, int]]
    targets=None,  # type: Optional[List[Dict[str, Tensor]]]
):
    # type: (...) -> Tuple[List[Dict[str, Tensor]], Dict[str, Tensor]]
    """
    Args:
	features (List[Tensor])
	proposals (List[Tensor[N, 4]])
	image_shapes (List[Tuple[H, W]])
	targets (List[Dict])
    """
    if targets is not None:
        for t in targets:
            # TODO: https://github.com/pytorch/pytorch/issues/26731
            floating_point_types = (torch.float, torch.double, torch.half)
            assert t["boxes"].dtype in floating_point_types, "target boxes must of float type"
            assert t["labels"].dtype == torch.int64, "target labels must of int64 type"
            if self.has_keypoint():
                assert t["keypoints"].dtype == torch.float32, "target keypoints must of float type"

    if self.training:
        proposals, matched_idxs, labels, regression_targets, length_labels = self.select_training_samples(proposals, targets)
    else:
        labels = None
        regression_targets = None
        matched_idxs = None

    box_features = self.box_roi_pool(features, proposals, image_shapes)
    box_features = self.box_head(box_features)
    class_logits, box_regression, length_logits = self.box_predictor(box_features)

    result: List[Dict[str, torch.Tensor]] = []
    losses = {}
    if self.training:
        assert labels is not None and regression_targets is not None and length_labels is not None
        loss_classifier, loss_box_reg, loss_length = fastrcnn_loss(class_logits, box_regression, labels, regression_targets, length_labels, length_logits)
        losses = {"loss_classifier": loss_classifier, "loss_box_reg": loss_box_reg, "loss_vessel_length": loss_length}
    else:
        boxes, scores, labels, lengths = postprocess_detections(class_logits, box_regression, proposals, image_shapes, length_logits)
        num_images = len(boxes)
        for i in range(num_images):
            result.append(
                {
                    "boxes": boxes[i],
                    "labels": labels[i],
                    "scores": scores[i],
                    "lengths": lengths[i]
                }
            )

    if self.has_mask():
        mask_proposals = [p["boxes"] for p in result]
        if self.training:
            assert matched_idxs is not None
            # during training, only focus on positive boxes
            num_images = len(proposals)
            mask_proposals = []
            pos_matched_idxs = []
            for img_id in range(num_images):
                pos = torch.where(labels[img_id] > 0)[0]
                mask_proposals.append(proposals[img_id][pos])
                pos_matched_idxs.append(matched_idxs[img_id][pos])
        else:
            pos_matched_idxs = None

        if self.mask_roi_pool is not None:
            mask_features = self.mask_roi_pool(features, mask_proposals, image_shapes)
            mask_features = self.mask_head(mask_features)
            mask_logits = self.mask_predictor(mask_features)
        else:
            raise Exception("Expected mask_roi_pool to be not None")

        loss_mask = {}
        if self.training:
            assert targets is not None
            assert pos_matched_idxs is not None
            assert mask_logits is not None

            gt_masks = [t["masks"] for t in targets]
            gt_labels = [t["labels"] for t in targets]
            rcnn_loss_mask = maskrcnn_loss(mask_logits, mask_proposals, gt_masks, gt_labels, pos_matched_idxs)
            loss_mask = {"loss_mask": rcnn_loss_mask}
        else:
            labels = [r["labels"] for r in result]
            masks_probs = maskrcnn_inference(mask_logits, labels)
            for mask_prob, r in zip(masks_probs, result):
                r["masks"] = mask_prob

        losses.update(loss_mask)

    # keep none checks in if conditional so torchscript will conditionally
    # compile each branch
    if (
        self.keypoint_roi_pool is not None
        and self.keypoint_head is not None
        and self.keypoint_predictor is not None
    ):
        keypoint_proposals = [p["boxes"] for p in result]
        if self.training:
            # during training, only focus on positive boxes
            num_images = len(proposals)
            keypoint_proposals = []
            pos_matched_idxs = []
            assert matched_idxs is not None
            for img_id in range(num_images):
                pos = torch.where(labels[img_id] > 0)[0]
                keypoint_proposals.append(proposals[img_id][pos])
                pos_matched_idxs.append(matched_idxs[img_id][pos])
        else:
            pos_matched_idxs = None

        keypoint_features = self.keypoint_roi_pool(features, keypoint_proposals, image_shapes)
        keypoint_features = self.keypoint_head(keypoint_features)
        keypoint_logits = self.keypoint_predictor(keypoint_features)

        loss_keypoint = {}
        if self.training:
            assert targets is not None
            assert pos_matched_idxs is not None

            gt_keypoints = [t["keypoints"] for t in targets]
            rcnn_loss_keypoint = keypointrcnn_loss(
                keypoint_logits, keypoint_proposals, gt_keypoints, pos_matched_idxs
            )
            loss_keypoint = {"loss_keypoint": rcnn_loss_keypoint}
        else:
            assert keypoint_logits is not None
            assert keypoint_proposals is not None

            keypoints_probs, kp_scores = keypointrcnn_inference(keypoint_logits, keypoint_proposals)
            for keypoint_prob, kps, r in zip(keypoints_probs, kp_scores, result):
                r["keypoints"] = keypoint_prob
                r["keypoints_scores"] = kps

        losses.update(loss_keypoint)

    return result, losses


def select_training_samples(
    self,
    proposals,  # type: List[Tensor]
    targets,  # type: Optional[List[Dict[str, Tensor]]]
):
    self.check_targets(targets)
    assert targets is not None
    dtype = proposals[0].dtype
    device = proposals[0].device

    gt_boxes = [t["boxes"].to(dtype) for t in targets]
    gt_labels = [t["labels"] for t in targets]
    gt_length_labels = [t["length_labels"] for t in targets]

    # append ground-truth bboxes to propos
    proposals = self.add_gt_proposals(proposals, gt_boxes)

    # get matching gt indices for each proposal
    matched_idxs, labels = self.assign_targets_to_proposals(proposals, gt_boxes, gt_labels)
    matched_idxs_vessels, length_labels = self.assign_targets_to_proposals(proposals, gt_boxes, gt_length_labels)

    # sample a fixed proportion of positive-negative proposals
    sampled_inds = self.subsample(labels)
    matched_gt_boxes = []
    num_images = len(proposals)
    for img_id in range(num_images):
        img_sampled_inds = sampled_inds[img_id]
        proposals[img_id] = proposals[img_id][img_sampled_inds]
        labels[img_id] = labels[img_id][img_sampled_inds]
        length_labels[img_id] = length_labels[img_id][img_sampled_inds]
        matched_idxs[img_id] = matched_idxs[img_id][img_sampled_inds]
        
        gt_boxes_in_image = gt_boxes[img_id]
        if gt_boxes_in_image.numel() == 0:
            gt_boxes_in_image = torch.zeros((1, 4), dtype=dtype, device=device)
        matched_gt_boxes.append(gt_boxes_in_image[matched_idxs[img_id]])

    regression_targets = self.box_coder.encode(matched_gt_boxes, proposals)
    return proposals, matched_idxs, labels, regression_targets, length_labels


def fastrcnn_loss(class_logits, box_regression, labels, regression_targets, length_labels, length_logits):
    # type: (Tensor, Tensor, List[Tensor], List[Tensor]) -> Tuple[Tensor, Tensor]
    """
    Computes the loss for Faster R-CNN.
    Args:
        class_logits (Tensor)
        box_regression (Tensor)
        labels (list[BoxList])
        regression_targets (Tensor)
        length_labels (list[BoxList])
        length_logits (Tensor)
    Returns:
        classification_loss (Tensor)
        box_loss (Tensor)
        length_loss (Tensor)
    """
    labels = torch.cat(labels, dim=0)

    length_labels = torch.cat(length_labels, dim=0)

    regression_targets = torch.cat(regression_targets, dim=0)

    valid_indices = length_labels > 0
    valid_length_logits = length_logits[valid_indices]
    valid_length_labels = length_labels[valid_indices]

    length_loss = F.mse_loss(valid_length_logits.squeeze().float(), valid_length_labels.squeeze().float())

    classification_loss = F.cross_entropy(class_logits, labels)

    # get indices that correspond to the regression targets for
    # the corresponding ground truth labels, to be used with
    # advanced indexing
    sampled_pos_inds_subset = torch.where(labels > 0)[0]
    labels_pos = labels[sampled_pos_inds_subset]
    N, num_classes = class_logits.shape
    box_regression = box_regression.reshape(N, box_regression.size(-1) // 4, 4)

    box_loss = F.smooth_l1_loss(
        box_regression[sampled_pos_inds_subset, labels_pos],
        regression_targets[sampled_pos_inds_subset],
        beta=1 / 9,
        reduction="sum",
    )
    box_loss = box_loss / labels.numel()

    return classification_loss, box_loss, length_loss


def postprocess_detections(
    class_logits,  # type: Tensor
    box_regression,  # type: Tensor
    proposals,  # type: List[Tensor]
    image_shapes,  # type: List[Tuple[int, int]]
    length_logits
):
    # type: (...) -> Tuple[List[Tensor], List[Tensor], List[Tensor]]
    device = class_logits.device
    num_classes = class_logits.shape[-1]

    box_coder = BoxCoder((10.0, 10.0, 5.0, 5.0))

    boxes_per_image = [boxes_in_image.shape[0] for boxes_in_image in proposals]
    pred_boxes = box_coder.decode(box_regression, proposals)

    pred_scores = F.softmax(class_logits, -1)

    pred_boxes_list = pred_boxes.split(boxes_per_image, 0)
    pred_scores_list = pred_scores.split(boxes_per_image, 0)
    pred_lengths_list = length_logits.split(boxes_per_image, 0)

    all_boxes = []
    all_scores = []
    all_labels = []
    all_lengths = []
    for boxes, scores, image_shape, lengths in zip(pred_boxes_list, pred_scores_list, image_shapes, pred_lengths_list):
        boxes = box_ops.clip_boxes_to_image(boxes, image_shape)

        # create labels for each prediction
        labels = torch.arange(num_classes, device=device)
        labels = labels.view(1, -1).expand_as(scores)

        # remove predictions with the background label
        boxes = boxes[:, 1:]
        scores = scores[:, 1:]
        labels = labels[:, 1:]

        # batch everything, by making every class prediction be a separate instance
        boxes = boxes.reshape(-1, 4)
        scores = scores.reshape(-1)
        labels = labels.reshape(-1)
        lengths = lengths.squeeze().repeat_interleave(3)

        # remove low scoring boxes
        inds = torch.where(scores > 0.05)[0]
        boxes, scores, labels, lengths = boxes[inds], scores[inds], labels[inds], lengths[inds]

        # remove empty boxes
        keep = box_ops.remove_small_boxes(boxes.to(device), min_size=1e-2)
        boxes, scores, labels, lengths = boxes[keep], scores[keep], labels[keep], lengths[keep]

        # non-maximum suppression, independently done per class
        keep = box_ops.batched_nms(boxes, scores, labels, 0.5)
        # keep only topk scoring predictions
        keep = keep[: 100]
        boxes, scores, labels, lengths = boxes[keep], scores[keep], labels[keep], lengths[keep]

        all_boxes.append(boxes)
        all_scores.append(scores)
        all_labels.append(labels)
        all_lengths.append(lengths)

    return all_boxes, all_scores, all_labels, all_lengths
