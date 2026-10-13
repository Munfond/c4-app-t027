"use client";

import { useRef, useState } from "react";
import Link from "next/link";

type Section = "start" | "read" | "agent";
const sections: {id: Section; label: string}[] = [{id:"start",label:"Bắt đầu"},{id:"read",label:"Hiểu kết quả"},{id:"agent",label:"Agent & CARLA"}];

export function UsageGuide({ onShowLab, onShowAgent }: { onShowLab: () => void; onShowAgent: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const [section, setSection] = useState<Section>("start");
  const close = () => dialog.current?.close();
  return <>
    <button type="button" className="usage-guide-trigger" aria-haspopup="dialog" aria-controls="usage-guide" onClick={() => {
      window.dispatchEvent(new Event("p027-pause-lab")); dialog.current?.showModal(); if(content.current)content.current.scrollTop=0;
    }}><span aria-hidden="true">?</span> Hướng dẫn</button>
    <dialog id="usage-guide" ref={dialog} className="usage-guide" aria-labelledby="usage-guide-title" aria-describedby="usage-guide-intro">
      <header className="usage-guide-header">
        <div><p className="eyebrow">PERCEPTION LAB / HƯỚNG DẪN</p><h2 id="usage-guide-title">Biết nhìn ở đâu.<br />Hiểu mình đang thấy gì.</h2></div>
        <form method="dialog"><button type="submit" className="usage-guide-close" aria-label="Đóng hướng dẫn">×</button></form>
      </header>
      <p id="usage-guide-intro" className="usage-guide-intro">Chọn một cảnh, xem cảm biến, rồi đối chiếu kết quả mô hình. Không cần biết công thức để bắt đầu.</p>
      <div className="usage-guide-sections" role="group" aria-label="Nội dung hướng dẫn">{sections.map(item => <button type="button" key={item.id} aria-pressed={section === item.id} onClick={() => {setSection(item.id);if(content.current)content.current.scrollTop=0;}}>{item.label}</button>)}</div>
      <div className="usage-guide-content" ref={content}>
        {section === "start" && <section aria-label="Bắt đầu xem Lab">
          <p className="usage-guide-lead">Lần đầu sử dụng? Đi theo 4 bước này.</p>
          <ol className="usage-guide-steps">
            <li><strong>Chọn cảnh và thời điểm</strong><p>Trong Lab, chọn <b>Scene</b> (một đoạn đường đã ghi) và <b>Frame</b> (một thời điểm). Trên điện thoại, mở <b>Thiết lập</b> để thấy các lựa chọn.</p></li>
            <li><strong>Quan sát đầu vào</strong><p>Mở <b>Cảm biến → Camera 360°</b> để hình dung cảnh. Chuyển sang <b>LiDAR + Radar</b>; bỏ tick cảm biến nào bạn muốn ẩn. Đổi <b>Màu LiDAR → Phân đoạn</b> để xem các nhóm điểm có màu theo lớp.</p></li>
            <li><strong>Xem mô hình hiểu cảnh thế nào</strong><p>Mở <b>Kết quả mô hình</b> và chọn Detection 3D, Seg3D, Occupancy hoặc Flow. Giữ nguyên frame để đối chiếu với camera; đọc tên model và sensor đầu vào đi kèm.</p></li>
            <li><strong>Phát liên tục hoặc xem từng frame</strong><p>Bấm <b>Phát</b>, đổi tốc độ hoặc bật <b>Lặp</b>. Muốn kiểm tra kỹ, tạm dừng rồi kéo thanh thời gian hoặc chuyển từng frame. Khi chuyển góc nhìn, playback dừng để bạn giữ đúng thời điểm.</p></li>
          </ol>
          <div className="usage-guide-actions"><Link href="/lab" onClick={() => {close();onShowLab();}}>Bắt đầu tại Lab →</Link></div>
        </section>}
        {section === "read" && <section aria-label="Hiểu đầu ra mô hình">
          <p className="usage-guide-lead">Các góc nhìn trả lời những câu hỏi khác nhau.</p>
          <dl className="usage-guide-definitions">
            <div><dt>Camera / LiDAR / Radar</dt><dd>Dữ liệu cảm biến để quan sát bối cảnh và vị trí điểm đo. Ảnh camera tham chiếu có thể được hiển thị ngay cả khi model không sử dụng camera.</dd></div>
            <div><dt>Detection 3D</dt><dd>Hộp dự đoán vị trí, hướng và kích thước vật thể. Hộp hoặc hình xe minh họa không phải kết quả phân đoạn 3D.</dd></div>
            <div><dt>Seg3D</dt><dd>Mỗi điểm được gán một nhóm ngữ nghĩa, ví dụ đường, xe hoặc người. Xem nguồn lớp và giới hạn chuyển dataset trước khi tin kết quả.</dd></div>
            <div><dt>Occupancy</dt><dd>Ô nào model cho là có vật thể, nền tĩnh hoặc trống. Bản hiện tại là lưới nhìn từ trên xuống (BEV), chưa phải bản đồ 3D đầy đủ.</dd></div>
            <div><dt>Flow / Risk</dt><dd>Flow ước lượng chuyển động giữa các thời điểm. Risk là điểm rủi ro thử nghiệm, chưa là xác suất va chạm hoặc kết luận an toàn.</dd></div>
          </dl>
          <p className="usage-guide-note"><b>Model</b> là dự đoán; <b>Reference</b> là nhãn hoặc hình học tham chiếu để đối chiếu. Trong preview CARLA, ô reference màu xám là vùng chưa quan sát, không được coi là trống. Dấu + là gốc xe mình; phía trước hướng lên trên.</p>
          <div className="usage-guide-actions"><Link href="/compare" onClick={() => {close();onShowLab();}}>So sánh hai model →</Link><Link href="/benchmarks" onClick={() => {close();onShowLab();}}>Xem chỉ số đánh giá →</Link></div>
          <p className="usage-guide-small">IoU đo mức chồng khớp với reference; cao hơn thường tốt hơn trên cùng dữ liệu. Độ trễ là thời gian xử lý. Chỉ so số đo khi nguồn dữ liệu, cách chấm và phạm vi đo tương thích.</p>
        </section>}
        {section === "agent" && <section aria-label="Sử dụng agent và mô phỏng CARLA">
          <p className="usage-guide-lead">Xem evidence đã có trước khi tạo lượt mô phỏng mới.</p>
          <ol className="usage-guide-steps">
            <li><strong>Mở bot cạnh bản đồ</strong><p>Bấm <b>Agent</b> ở góc dưới. Chọn <b>nuScenes replay</b> để thử dữ liệu ghi sẵn, hoặc <b>CARLA</b> để làm việc với mô phỏng.</p></li>
            <li><strong>Xem policy đã học hoạt động</strong><p>Với CARLA, mở <b>PPO trong CARLA · xem quyết định từng frame → Xem capture & quyết định</b>. Bấm Phát để xem camera, occupancy và cấu hình LiDAR cùng frame. Đây là phát lại lượt chạy đã ghi, không phải mở simulator live.</p></li>
            <li><strong>Đọc bằng chứng của đề xuất</strong><p>Mở mục <b>Học tăng cường · 12 cấu hình LiDAR CARLA</b> để đối chiếu PPO với cấu hình cố định, chỉ số và nguồn báo cáo. Nếu không tốt hơn, giữ cấu hình cũ. Mở phần đánh giá để engineer ghi nhận lý do.</p></li>
            <li><strong>Tạo thí nghiệm khi máy đủ điều kiện</strong><p>Mở <b>Cấu hình nâng cao</b>, chọn map, thời tiết, số frame và FOV camera, rồi <b>Tạo thí nghiệm</b>. <b>queued</b> nghĩa là chờ worker; <b>running · capture</b> nghĩa là đang thu dữ liệu; <b>succeeded</b> mới có kết quả hoàn tất. Xem bản ghi không cần GPU; tạo capture mới cần CARLA, GPU khỏe và đủ RAM.</p></li>
          </ol>
          <p className="usage-guide-note"><b>PPO</b> (Proximal Policy Optimization) là thuật toán học tăng cường dùng để chọn cấu hình. Policy hiện chọn LiDAR cho frame kế tiếp; chưa điều khiển xe, chưa tự thay camera/radar/model. Clip “lịch cố định” chỉ kiểm tra chuyển sensor, không phải agent tự thích nghi.</p>
          <div className="usage-guide-actions"><button type="button" onClick={() => {close();onShowAgent();}}>Mở agent · CARLA →</button></div>
          <details className="usage-guide-troubleshooting"><summary>Nếu không thấy ảnh hoặc job mãi chưa chạy?</summary><p>Chọn một lượt <b>succeeded</b> để xem trước. Job queued cần worker; lỗi capture cần kiểm tra GPU/RAM và log. Khi thiếu nguồn dữ liệu hoặc reference, hệ thống báo thiếu thay vì tạo kết quả giả. Nếu ảnh camera bị chặn bảo vệ, cần cache đã xử lý làm mờ; không bật ảnh thô để né lỗi.</p><p>Trong lượt CARLA hiện tại, mưa/sương mù trên ảnh chỉ giúp xem bối cảnh; chưa chứng minh model LiDAR bền hơn dưới thời tiết xấu. FOV là góc nhìn: 60° hẹp, 90° cân bằng, 110° rộng; chưa phải chỉnh điểm lấy nét.</p></details>
        </section>}
      </div>
      <footer className="usage-guide-footer"><span>Giữ cùng scene & frame khi đối chiếu.</span><button type="button" onClick={close}>Đã hiểu</button></footer>
    </dialog>
  </>;
}
