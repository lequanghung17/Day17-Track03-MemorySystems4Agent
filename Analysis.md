# Phân tích kết quả benchmark

## Kết quả tóm tắt

### Standard Benchmark

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 3157 | 23322 | 0.04 | 0.27 | 0 | 0 |
| Advanced | 2512 | 32418 | 1.00 | 0.99 | 520 | 0 |

### Long-Context Stress Benchmark

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 977 | 28709 | 0.00 | 0.24 | 0 | 0 |
| Advanced | 1021 | 21673 | 1.00 | 0.99 | 1012 | 17 |

## Vì sao Advanced recall tốt hơn Baseline

Baseline chỉ giữ memory trong từng thread. Khi benchmark hỏi recall bằng một thread mới, Baseline không còn truy cập được các facts đã xuất hiện ở thread trước, nên điểm cross-session recall rất thấp.

Advanced lưu các facts bền vững vào `User.md`, ví dụ tên, nơi ở, nghề nghiệp, style trả lời, đồ uống yêu thích và các mối quan tâm kỹ thuật. Khi sang thread mới, agent đọc lại `User.md` nên vẫn trả lời được các câu hỏi recall. Vì vậy Advanced đạt recall 1.00 trong cả standard benchmark và stress benchmark.

## Vì sao Advanced có thể tốn hơn ở hội thoại ngắn

Trong Standard Benchmark, Advanced xử lý 32418 prompt tokens, cao hơn Baseline với 23322 prompt tokens. Lý do là Advanced không chỉ mang theo lịch sử gần nhất, mà còn đưa thêm persistent profile từ `User.md` vào context.

Với hội thoại ngắn, chi phí thêm này có thể chưa được bù lại bằng compact memory, vì thread chưa dài đến mức cần nén. Nói cách khác, Advanced mua khả năng nhớ dài hạn bằng cách thêm một lớp memory vào prompt.

## Vì sao compact có lợi thế ở hội thoại dài

Trong Long-Context Stress Benchmark, Baseline phải xử lý 28709 prompt tokens vì tiếp tục mang theo lịch sử hội thoại dài. Advanced chỉ xử lý 21673 prompt tokens, dù có thêm `User.md`, vì compact memory đã kích hoạt 17 lần.

Compact giúp đưa các message cũ vào summary và chỉ giữ lại một số message gần nhất. Cách này giữ đủ ngữ cảnh chính cho recall và follow-up, nhưng giảm lượng prompt cần xử lý mỗi turn. Lợi thế của compact vì thế rõ nhất ở hội thoại dài, không phải ở hội thoại ngắn.

## Memory growth và rủi ro

Advanced có memory growth 520 bytes trong Standard Benchmark và 1012 bytes trong Stress Benchmark. Đây là chi phí thật của persistent memory: agent nhớ được nhiều hơn, nhưng file `User.md` sẽ tăng dần theo thời gian.

Rủi ro chính là lưu sai fact hoặc không cập nhật đúng khi user đính chính. Ví dụ nếu agent lưu câu hỏi thành fact, `User.md` có thể bị nhiễm thông tin sai và làm recall sai ở các session sau. Ngoài ra, nếu không có cơ chế lọc, decay, hoặc compact profile, file memory có thể phình to và làm prompt tokens tăng trở lại.

Kết luận: Advanced mạnh hơn Baseline về cross-session recall, nhưng đổi lại hệ thống phức tạp hơn và cần guardrail tốt hơn để tránh lưu sai, lưu thừa, hoặc để memory file tăng không kiểm soát.
