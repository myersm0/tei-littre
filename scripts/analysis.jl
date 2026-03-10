using JSON3
using LinearAlgebra
using GLMakie
using UMAP
using StatsBase
using Random

embedding_dir = "data/embeddings"
jsonl_files = filter(f -> endswith(f, ".jsonl"), readdir(embedding_dir; join = true))
sort!(jsonl_files)

struct IndentRecord
	id::String
	entry::String
	variante::String
	indent::String
	text::String
	embedding::Vector{Float64}
end

function load_jsonl(path)
	records = IndentRecord[]
	for line in eachline(path)
		d = JSON3.read(line)
		id = d[:id]
		parts = split(id, ".")
		entry = join(parts[1:end-2], ".")
		variante = parts[end-1]
		indent = parts[end]
		text = get(d, :text, id)
		emb = Float64.(d[:embedding])
		push!(records, IndentRecord(id, entry, variante, indent, text, emb))
	end
	return records
end

println("Loading embeddings...")
records = vcat([load_jsonl(f) for f in jsonl_files]...)
println("  $(length(records)) items from $(length(jsonl_files)) files")

X = reduce(hcat, [Float32.(r.embedding) for r in records])'

# PCA to 50 dims before UMAP
X_mean = vec(mean(X; dims = 1))
X_zm = X .- X_mean'
svd_result = svd(X_zm)
X_pca = X_zm * svd_result.V[:, 1:50]
println("  Variance retained: $(round(sum(svd_result.S[1:50].^2) / sum(svd_result.S.^2) * 100; digits = 1))%")

X = X_pca

function classify_heuristic(text::String)
	bare = let idx = findfirst(": ", text)
		idx === nothing ? text : text[idx[2]+1:end]
	end
	bare = lstrip(bare)
	startswith(bare, "Terme d") && return :domain
	startswith(bare, "Fig.") && return :figurative
	startswith(bare, "Figurément") && return :figurative
	any(p -> startswith(bare, p), [
		"Familièrement", "Populairement", "Par extension",
		"Par analogie", "Poétiquement", "Ironiquement",
	]) && return :register
	any(p -> startswith(bare, p), [
		"Il se dit", "On dit", "Se dit",
	]) && return :elaboration
	comma = findfirst(',', bare)
	if comma !== nothing && 3 < comma < 60
		return :possible_locution
	end
	return :other
end

labels = classify_heuristic.(getfield.(records, :text))
label_counts = countmap(labels)
for (k, v) in sort(collect(label_counts); by = last, rev = true)
	println("  $k: $v")
end

entry_names = getfield.(records, :entry)
unique_entries = unique(entry_names)
entry_to_indices = Dict(e => findall(==(e), entry_names) for e in unique_entries)

umap_sample_fraction = 0.3

# sample by headword for UMAP (all indents from selected entries)
rng = MersenneTwister(42)
sampled_entries = shuffle(rng, unique_entries)[1:round(Int, length(unique_entries) * umap_sample_fraction)]
sample_mask = findall(e -> e in Set(sampled_entries), entry_names)
println("  UMAP sample: $(length(sample_mask)) indents from $(length(sampled_entries)) entries")

umap_raw = UMAP.fit(X[sample_mask, :]', 2; n_neighbors = 30, min_dist = 0.1)

X_centered = copy(X)
for (entry, indices) in entry_to_indices
	length(indices) < 3 && continue
	centroid = vec(mean(X[indices, :]; dims = 1))
	X_centered[indices, :] .-= centroid'
end

umap_centered = UMAP.fit(X_centered[sample_mask, :]', 2; n_neighbors = 30, min_dist = 0.1)

role_colors = Dict(
	:domain => :red,
	:figurative => :orange,
	:register => :purple,
	:elaboration => :green,
	:possible_locution => :steelblue,
	:other => :gray80,
)

draw_order = [:other, :possible_locution, :elaboration, :register, :figurative, :domain]

#make_umap_plot(umap_raw, labels, records, "Raw embeddings ($(length(records)) items)")
#make_umap_plot(umap_centered, labels, records, "Centered embeddings ($(length(records)) items)")
xy = umap_centered
sampled_labels = labels[sample_mask]
sampled_records = records[sample_mask]
title_str = "Centered embeddings ($(length(sample_mask)) items)"

fig = Figure(size = (1200, 800))
ax = Axis(fig[1, 1]; title = title_str, xlabel = "UMAP 1", ylabel = "UMAP 2")

for role in draw_order
	mask = findall(==(role), sampled_labels)
	isempty(mask) && continue
	scatter!(
		ax, [xy.embedding[j][1] for j in mask], [xy.embedding[j][2] for j in mask];
		markersize = 4,
		alpha = 0.5,
		color = role_colors[role],
		label = string(role),
		inspector_label = (self, i, p) -> sampled_records[mask[i]].id * "\n" * first(sampled_records[mask[i]].text, 120),
	)
end

axislegend(ax; position = :rt)
DataInspector(fig)


# ============================================================
# 6. Linear probe: locution vs non-locution (Opus labels)
# ============================================================

opus_label_path = "llm_opus_locution.json"

println("\n--- Linear probe (Opus labels) ---")
println("  Loading $opus_label_path...")

opus_raw = JSON3.read(read(opus_label_path, String))
opus_by_id = Dict{String, Bool}()
for record in opus_raw
	indent_id = get(record, :indent_id, nothing)
	is_target = get(record, :is_target, nothing)
	indent_id === nothing && continue
	is_target === nothing && continue
	opus_by_id[indent_id] = is_target
end
println("  $(length(opus_by_id)) Opus labels loaded")

record_id_to_idx = Dict(r.id => i for (i, r) in enumerate(records))

opus_indices = Int[]
opus_labels = Float64[]
for (indent_id, is_locution) in opus_by_id
	idx = get(record_id_to_idx, indent_id, nothing)
	idx === nothing && continue
	push!(opus_indices, idx)
	push!(opus_labels, is_locution ? 1.0 : 0.0)
end

n_matched = length(opus_indices)
n_pos = sum(opus_labels .== 1.0)
n_neg = sum(opus_labels .== 0.0)
println("  Matched to embeddings: $n_matched ($n_pos locution, $n_neg continuation)")

opus_entries = [records[i].entry for i in opus_indices]
unique_opus_entries = unique(opus_entries)

rng = MersenneTwister(42)
shuffled_entries = shuffle(rng, unique_opus_entries)
split_point = round(Int, 0.8 * length(shuffled_entries))
train_entries = Set(shuffled_entries[1:split_point])
test_entries = Set(shuffled_entries[split_point + 1:end])

train_mask = [opus_entries[i] in train_entries for i in eachindex(opus_entries)]
test_mask = .!train_mask

X_opus = X[opus_indices, :]
X_train = X_opus[train_mask, :]
y_train = opus_labels[train_mask]
X_test = X_opus[test_mask, :]
y_test = opus_labels[test_mask]

println("  Train: $(size(X_train, 1)) items ($(sum(y_train .== 1.0)) pos) from $(length(train_entries)) entries")
println("  Test:  $(size(X_test, 1)) items ($(sum(y_test .== 1.0)) pos) from $(length(test_entries)) entries")

function ridge_classify(X_train, y_train, X_test, y_test; ridge_lambda = 1.0)
	X_aug = hcat(X_train, ones(size(X_train, 1)))
	w = (X_aug' * X_aug + ridge_lambda * I) \ (X_aug' * y_train)
	X_test_aug = hcat(X_test, ones(size(X_test, 1)))
	y_pred = X_test_aug * w .> 0.5
	accuracy = mean(y_pred .== y_test)
	precision_val = sum((y_pred .== 1) .& (y_test .== 1)) / max(sum(y_pred .== 1), 1)
	recall_val = sum((y_pred .== 1) .& (y_test .== 1)) / max(sum(y_test .== 1), 1)
	f1 = 2 * precision_val * recall_val / max(precision_val + recall_val, 1e-10)
	return (; accuracy, precision_val, recall_val, f1, w)
end

function print_metrics(label, metrics)
	println("  $label:")
	println("    Accuracy:  $(round(metrics.accuracy; digits = 3))")
	println("    Precision: $(round(metrics.precision_val; digits = 3))")
	println("    Recall:    $(round(metrics.recall_val; digits = 3))")
	println("    F1:        $(round(metrics.f1; digits = 3))")
end

raw_metrics = ridge_classify(X_train, y_train, X_test, y_test)
print_metrics("Raw embeddings", raw_metrics)

X_centered_opus = X_centered[opus_indices, :]
X_train_c = X_centered_opus[train_mask, :]
X_test_c = X_centered_opus[test_mask, :]

centered_metrics = ridge_classify(X_train_c, y_train, X_test_c, y_test)
print_metrics("Centered embeddings", centered_metrics)



