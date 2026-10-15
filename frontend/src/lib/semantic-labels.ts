export const SEMANTIC_LABELS: Record<string, string> = {
  unlabeled: "Chưa gán lớp", car: "Xe con", bicycle: "Xe đạp", motorcycle: "Xe máy", truck: "Xe tải",
  "other-vehicle": "Xe khác", person: "Người", rider: "Người trên xe", bicyclist: "Người đi xe đạp",
  motorcyclist: "Người đi xe máy", road: "Mặt đường", parking: "Bãi đỗ", sidewalk: "Vỉa hè",
  "other-ground": "Nền khác", building: "Nhà / mặt dựng", wall: "Tường", fence: "Hàng rào",
  vegetation: "Cây xanh", trunk: "Thân cây", terrain: "Địa hình", pole: "Cột", sky: "Bầu trời",
  "traffic-sign": "Biển báo", "traffic sign": "Biển báo", "traffic light": "Đèn tín hiệu", bus: "Xe buýt", train: "Tàu",
};

export type SemanticClass = { id: number; name: string; color: string };
