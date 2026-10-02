import json, statistics, sys

p = r"C:\Users\silvi\Desktop\licenta2026\app\nlp-service\reports\latency_profile_20260617.json"
d = json.load(open(p, encoding="utf-8"))

def pct(v, q):
    v = sorted(v)
    k = (len(v) - 1) * q / 100
    f = int(k)
    c = min(f + 1, len(v) - 1)
    return v[f] if f == c else v[f] + (v[c] - v[f]) * (k - f)

m = d["warm_measurements"]
print("n_pairs =", len(m))
print("n_warmup =", d["n_warmup"], " n_measure_cvs =", d["n_measure_cvs"], " n_jds =", d["n_jds"])
print("cpu =", d["cpu"])
print("python =", d["python_version"])
print("encoder =", d["encoder_path"])
print("cold_total_ms =", d["cold_total_ms"])

stats = {}
for key in ("extract_ms", "skill_extract_ms", "link_ms", "score_ms"):
    vals = [x[key] for x in m]
    mean = statistics.fmean(vals)
    p50 = pct(vals, 50)
    p90 = pct(vals, 90)
    stats[key] = (mean, p50, p90)
    print(f"{key}: mean={mean:.3f} ms | p50={p50:.3f} ms | p90={p90:.3f} ms | n={len(vals)}")

# t_upload = extract + skill_extract + link; t_match = score (seconds)
em, ep = stats["extract_ms"][0], stats["extract_ms"][1]
sm, sp = stats["skill_extract_ms"][0], stats["skill_extract_ms"][1]
lm, lp = stats["link_ms"][0], stats["link_ms"][1]
cm, cp = stats["score_ms"][0], stats["score_ms"][1]

t_upload_mean_s = (em + sm + lm) / 1000.0
t_match_mean_s = cm / 1000.0
t_total_mean_s = t_upload_mean_s + t_match_mean_s
reduction_pct = 100.0 * t_upload_mean_s / t_total_mean_s if t_total_mean_s else 0.0

print()
print(f"t_upload (mean, s) = {t_upload_mean_s:.3f}")
print(f"t_match  (mean, s) = {t_match_mean_s:.3f}")
print(f"t_total  (mean, s) = {t_total_mean_s:.3f}")
print(f"reduction_at_click_pct = {reduction_pct:.1f}")

cold_s = (d["cold_total_ms"] or 0.0) / 1000.0
print(f"cold_total_s = {cold_s:.3f}")

for N in (50, 150, 400):
    print(f"N={N}: upload={N*t_upload_mean_s:.3f} s | match={N*t_match_mean_s:.3f} s | naiv={N*t_total_mean_s:.3f} s")
