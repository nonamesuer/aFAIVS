from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any


DEFAULT_VISION_FUSION = {"enabled": True,"lowConfidence": 0.15,"classMargin": 0.08,"wrongObjectConfirmMs": 600,"missingGraceMs": 1000,"targetConfirmMs": 350,"releaseConfirmMs": 250,"trackMaxDistance": 120,"trackMaxMissingMs": 1200,"identityLock": True}


def normalize_vision_fusion(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_VISION_FUSION)
    result["enabled"] = bool(raw.get("enabled", result["enabled"]))
    result["identityLock"] = bool(raw.get("identityLock", result["identityLock"]))
    for key in ("lowConfidence","classMargin"):
        try:result[key] = max(0.0, min(1.0, float(raw.get(key, result[key]))))
        except (TypeError, ValueError):pass
    for key in ("wrongObjectConfirmMs","missingGraceMs","targetConfirmMs","releaseConfirmMs","trackMaxDistance","trackMaxMissingMs"):
        try:result[key] = max(0, int(raw.get(key, result[key])))
        except (TypeError, ValueError):pass
    return result


def _xyxy(item: dict[str, Any]) -> tuple[float, float, float, float] | None:
    points = item.get("points") or item.get("bbox") or []
    try:
        if len(points) == 2:return float(points[0][0]),float(points[0][1]),float(points[1][0]),float(points[1][1])
        if len(points) == 4:return tuple(float(value) for value in points)  # type: ignore[return-value]
    except (TypeError, ValueError, IndexError):pass
    return None


def _iou(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    x1,y1,x2,y2 = max(left[0],right[0]),max(left[1],right[1]),min(left[2],right[2]),min(left[3],right[3])
    intersection = max(0.0,x2-x1)*max(0.0,y2-y1)
    if intersection <= 0:return 0.0
    left_area = max(0.0,left[2]-left[0])*max(0.0,left[3]-left[1]);right_area = max(0.0,right[2]-right[0])*max(0.0,right[3]-right[1])
    return intersection/max(1e-6,left_area+right_area-intersection)


def _distance(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    return math.dist(((left[0]+left[2])/2,(left[1]+left[3])/2),((right[0]+right[2])/2,(right[1]+right[3])/2))


@dataclass
class _Track:
    id: int
    box: tuple[float, float, float, float]
    last_seen: float
    scores: dict[str, float] = field(default_factory=dict)


class LightweightObjectTracker:
    """A small class-agnostic tracker used to retain identity across short occlusions/class flips."""

    def __init__(self, high_confidence: float, config: dict[str, Any] | None = None):
        self.high_confidence = max(0.0,min(1.0,float(high_confidence)))
        self.config = normalize_vision_fusion(config)
        self._tracks: dict[int,_Track] = {};self._next_id = 1

    def reset(self) -> None:self._tracks.clear();self._next_id = 1

    def update(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = time.monotonic();max_missing = self.config["trackMaxMissingMs"]/1000.0
        self._tracks = {track_id:track for track_id,track in self._tracks.items() if now-track.last_seen <= max_missing}
        result: list[dict[str, Any]] = [];available = set(self._tracks)
        for raw in sorted(items,key=lambda item:float(item.get("score",0) or 0),reverse=True):
            item = dict(raw);box = _xyxy(item)
            if box is None or int(item.get("class_id",0) or 0) == -1:item.update({"high_confidence":True,"classification_state":"confirmed"});result.append(item);continue
            best_id = None;best_cost = float("inf")
            for track_id in available:
                track = self._tracks[track_id];overlap = _iou(box,track.box);distance = _distance(box,track.box)
                if overlap < 0.05 and distance > self.config["trackMaxDistance"]:continue
                cost = distance-self.config["trackMaxDistance"]*overlap
                if cost < best_cost:best_id,best_cost = track_id,cost
            if best_id is None:
                best_id = self._next_id;self._next_id += 1;self._tracks[best_id] = _Track(best_id,box,now)
            else:available.remove(best_id)
            track = self._tracks[best_id];track.box = box;track.last_seen = now
            candidates = item.get("top_k") if isinstance(item.get("top_k"),list) else [{"label":item.get("label","").strip(),"score":float(item.get("score",0) or 0)}]
            incoming = {str(entry.get("label","")).strip():float(entry.get("score",0) or 0) for entry in candidates if isinstance(entry,dict) and str(entry.get("label","")).strip()}
            for label in set(track.scores)|set(incoming):track.scores[label] = incoming[label] if label not in track.scores else track.scores[label]*0.65+incoming.get(label,0.0)*0.35
            fused = sorted(track.scores.items(),key=lambda entry:entry[1],reverse=True);top_label,top_score = fused[0] if fused else (str(item.get("label","")),float(item.get("score",0) or 0));second_score = fused[1][1] if len(fused)>1 else 0.0
            margin = top_score-second_score;confirmed = top_score >= self.high_confidence and margin >= self.config["classMargin"]
            item.update({"raw_label":item.get("label",top_label),"label":top_label,"track_id":best_id,"fused_top_k":[{"label":label,"score":round(score,4)} for label,score in fused[:3]],"class_margin":round(margin,4),"high_confidence":top_score >= self.high_confidence,"classification_state":"confirmed" if confirmed else "ambiguous"})
            result.append(item)
        return result
