using MessagePack;

// UmaServer — servidor privado (sandbox) Umamusume Steam Global. Puerto 5090.
// El cliente (con el proxy en modo bypass+redirect) habla MessagePack PLANO:
//   request  = MessagePack del cuerpo (sin coneshell)
//   response = MessagePack del envelope {response_code, data_headers, data}
// Reproduce seeds capturados en umma/seeds/<path__con__>.resp.bin; si falta, devuelve
// un envelope minimo. Parchea data_headers.servertime a la hora actual.

var builder = WebApplication.CreateBuilder(args);
if (string.IsNullOrEmpty(builder.Configuration["urls"]) &&
    string.IsNullOrEmpty(Environment.GetEnvironmentVariable("ASPNETCORE_URLS")))
    builder.WebHost.UseUrls("http://0.0.0.0:5090");
var app = builder.Build();
var log = app.Logger;

string root = FindRepoRoot(AppContext.BaseDirectory);
string seedDir = Path.Combine(root, "seeds");
// Pool de personajes que la cuenta YA posee (de load/index card_list) para variar el gacha
// sin sacar unidades nuevas (que congelarian el cliente).
uint[] ownedCards = LoadOwnedCards(Path.Combine(seedDir, "load_index.resp.bin"));
string reqDir = Path.Combine(root, "live_requests");
Directory.CreateDirectory(reqDir);
log.LogInformation("UmaServer :5090  seeds={Seed}", seedDir);

app.MapGet("/", () => "UmaServer up (MessagePack plano).");

app.MapPost("/{**path}", async (HttpRequest http, string path) =>
{
    using var ms = new MemoryStream();
    await http.Body.CopyToAsync(ms);
    var body = ms.ToArray();

    var rel = path.StartsWith("umamusume/") ? path["umamusume/".Length..] : path;
    var safe = rel.Replace('/', '_');
    // log del request en claro (para depurar/seed)
    try { await File.WriteAllBytesAsync(Path.Combine(reqDir, safe + ".req.bin"), body); } catch { }

    // Selección de seed. El cliente rechaza respuestas re-serializadas (valida bytes
    // exactos), así que servimos SIEMPRE bytes oficiales crudos. Para gacha/exec
    // elegimos el seed según draw_num (1 vs 10): gacha_exec.d<N>.resp.bin.
    var seedFile = Path.Combine(seedDir, safe + ".resp.bin");
    if (rel is "gacha/exec")
    {
        int dn = DrawNum(body);
        var byDraw = Path.Combine(seedDir, $"{safe}.d{dn}.resp.bin");
        if (File.Exists(byDraw)) seedFile = byDraw;
    }
    byte[] resp;
    if (File.Exists(seedFile))
    {
        resp = await File.ReadAllBytesAsync(seedFile);   // bytes oficiales exactos
        resp = BinPatchCarats(resp);                     // fcoin -> 999999 (parche binario)
        if (rel is "gacha/exec" && ownedCards.Length > 0)
            resp = BinSwapGachaCards(resp, ownedCards);  // variar personajes (solo de los poseidos)
        log.LogInformation("{Path} -> {File} ({Bytes}B)", rel, Path.GetFileName(seedFile), resp.Length);
    }
    else
    {
        resp = MinimalEnvelope();
        log.LogWarning("{Path} -> SIN seed, envelope minimo", rel);
    }
    return Results.Bytes(resp, "application/x-msgpack");
});

try { app.Run(); }
catch (IOException)
{
    Console.WriteLine("\n[!] Puerto 5090 en uso? Cierra la otra instancia.");
    Console.WriteLine("Pulsa una tecla..."); Console.ReadKey();
}

// Parchea la respuesta: servertime fresco, carats (coin_info) a 999999 en cualquier
// respuesta, y para gacha/exec genera draw_num cartas (lo capturado solo tenia 1).
static byte[] PatchResponse(byte[] seed, string path, byte[] reqBody)
{
    var MP = MessagePack.Resolvers.ContractlessStandardResolver.Options;
    try
    {
        var obj = MessagePackSerializer.Deserialize<object>(seed, MP);
        if (obj is not IDictionary<object, object> root) return seed;

        if (Get(root, "data_headers") is IDictionary<object, object> dh)
            dh["servertime"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

        if (Get(root, "data") is IDictionary<object, object> data)
        {
            MaxCarats(data);
            if (path is "gacha/exec") ExpandGacha(data, reqBody);
        }
        return MessagePackSerializer.Serialize(obj, MP);
    }
    catch { return seed; }
}

static object? Get(IDictionary<object, object> d, string k) => d.TryGetValue(k, out var v) ? v : null;

// Re-serializa poniendo coin_info.fcoin/coin = 999999 (carats del gacha).
static byte[] PatchCarats(byte[] seed)
{
    var MP = MessagePack.Resolvers.ContractlessStandardResolver.Options;
    try
    {
        var obj = MessagePackSerializer.Deserialize<object>(seed, MP);
        if (obj is IDictionary<object, object> root
            && Get(root, "data") is IDictionary<object, object> data
            && Get(data, "coin_info") is IDictionary<object, object> ci)
        {
            ci["fcoin"] = 999999L;
            if (ci.ContainsKey("coin")) ci["coin"] = 999999L;
            return MessagePackSerializer.Serialize(obj, MP);
        }
    }
    catch { }
    return seed;
}

// Parche binario: pone el valor de toda clave MessagePack "fcoin" (carats) a 999999,
// sin re-serializar el resto (el cliente valida los bytes exactos del oficial).
static byte[] BinPatchCarats(byte[] data)
{
    byte[] key = { 0xA5, (byte)'f', (byte)'c', (byte)'o', (byte)'i', (byte)'n' };
    byte[] newVal = { 0xCE, 0x00, 0x0F, 0x42, 0x3F }; // uint32 999999
    var outBuf = new List<byte>(data.Length + 16);
    int i = 0;
    while (i < data.Length)
    {
        if (i + key.Length < data.Length && data.AsSpan(i, key.Length).SequenceEqual(key))
        {
            outBuf.AddRange(key);
            int vp = i + key.Length;
            int w = IntWidth(data[vp]);          // ancho del entero actual
            outBuf.AddRange(newVal);             // sustituir por uint32 999999
            i = vp + w;                          // saltar el entero viejo
            continue;
        }
        outBuf.Add(data[i]); i++;
    }
    return outBuf.ToArray();
}
// Lee los card_id de data.card_list (personajes poseidos) del seed load/index.
static uint[] LoadOwnedCards(string loadIndexSeed)
{
    try
    {
        if (!File.Exists(loadIndexSeed)) return Array.Empty<uint>();
        var o = MessagePackSerializer.Deserialize<object>(File.ReadAllBytes(loadIndexSeed),
            MessagePack.Resolvers.ContractlessStandardResolver.Options);
        if (o is IDictionary<object, object> root
            && Get(root, "data") is IDictionary<object, object> data
            && Get(data, "card_list") is object[] cards)
        {
            var ids = new List<uint>();
            foreach (var c in cards)
                if (c is IDictionary<object, object> cd && cd.TryGetValue("card_id", out var v))
                    try { uint id = Convert.ToUInt32(v); if (id > 65535) ids.Add(id); } catch { }
            return ids.ToArray();
        }
    }
    catch { }
    return Array.Empty<uint>();
}

// Intercambia card_id/piece_id de gacha_result_list por personajes poseidos (uint32 mismo ancho).
static byte[] BinSwapGachaCards(byte[] data, uint[] owned)
{
    byte[] kCard = { 0xA7, (byte)'c', (byte)'a', (byte)'r', (byte)'d', (byte)'_', (byte)'i', (byte)'d' };
    byte[] kPiece = { 0xA8, (byte)'p', (byte)'i', (byte)'e', (byte)'c', (byte)'e', (byte)'_', (byte)'i', (byte)'d' };
    var b = (byte[])data.Clone();
    uint pick = owned[0];
    for (int i = 0; i + 9 < b.Length; i++)
    {
        bool card = b.AsSpan(i, kCard.Length).SequenceEqual(kCard);
        bool piece = !card && i + kPiece.Length < b.Length && b.AsSpan(i, kPiece.Length).SequenceEqual(kPiece);
        if (!card && !piece) continue;
        int klen = card ? kCard.Length : kPiece.Length;
        int vp = i + klen;
        if (b[vp] != 0xCE) continue;                 // solo si el valor es uint32 (mismo ancho)
        if (card) pick = owned[Random.Shared.Next(owned.Length)];  // nuevo personaje por entrada
        b[vp + 1] = (byte)(pick >> 24); b[vp + 2] = (byte)(pick >> 16);
        b[vp + 3] = (byte)(pick >> 8);  b[vp + 4] = (byte)pick;        // card_id y su piece_id = mismo id
        i = vp + 4;
    }
    return b;
}

static int IntWidth(byte t) => t switch
{
    < 0x80 => 1, 0xCC => 2, 0xCD => 3, 0xCE => 5, 0xCF => 9,
    0xD0 => 2, 0xD1 => 3, 0xD2 => 5, 0xD3 => 9, >= 0xE0 => 1, _ => 1
};

static int DrawNum(byte[] reqBody)
{
    try
    {
        if (MessagePackSerializer.Deserialize<object>(reqBody, MessagePack.Resolvers.ContractlessStandardResolver.Options)
            is IDictionary<object, object> req && req.TryGetValue("draw_num", out var dn))
            return Convert.ToInt32(dn);
    }
    catch { }
    return 1;
}

// coin_info.fcoin (carats) y coin a 999999, en data y en cualquier sub-dict.
static void MaxCarats(IDictionary<object, object> data)
{
    if (Get(data, "coin_info") is IDictionary<object, object> ci)
    {
        ci["fcoin"] = 999999L;
        if (ci.ContainsKey("coin")) ci["coin"] = 999999L;
    }
}

// gacha/exec: replica la primera carta hasta draw_num veces (tiro de 10 = 10 cartas).
static void ExpandGacha(IDictionary<object, object> data, byte[] reqBody)
{
    int drawNum = 1;
    try
    {
        if (MessagePackSerializer.Deserialize<object>(reqBody, MessagePack.Resolvers.ContractlessStandardResolver.Options) is IDictionary<object, object> req
            && Get(req, "draw_num") is { } dn) drawNum = Convert.ToInt32(dn);
    }
    catch { }
    if (drawNum < 1) drawNum = 1;

    if (Get(data, "gacha_result_list") is object[] list && list.Length > 0)
    {
        var first = list[0];
        var expanded = new object[drawNum];
        for (int i = 0; i < drawNum; i++) expanded[i] = first; // misma carta x N (sandbox)
        data["gacha_result_list"] = expanded;

        // Escalar reward_summary_info para que cuadre con drawNum cartas.
        if (Get(data, "reward_summary_info") is IDictionary<object, object> rs)
        {
            ScaleList(Get(rs, "add_piece_list") as object[], "piece_num", drawNum);
            ScaleList(Get(rs, "add_item_list") as object[], "number", drawNum);
        }
    }
}

static void ScaleList(object[]? arr, string numKey, int factor)
{
    if (arr is null) return;
    foreach (var e in arr)
        if (e is IDictionary<object, object> d && d.TryGetValue(numKey, out var v))
            try { d[numKey] = Convert.ToInt64(v) * factor; } catch { }
}

static byte[] MinimalEnvelope()
{
    var env = new Dictionary<object, object>
    {
        ["response_code"] = 1,
        ["data_headers"] = new Dictionary<object, object>
        {
            ["viewer_id"] = 939072443663L,
            ["sid"] = "",
            ["servertime"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            ["result_code"] = 1,
        },
        ["data"] = new Dictionary<object, object>(),
    };
    return MessagePackSerializer.Serialize(env,
        MessagePack.Resolvers.ContractlessStandardResolver.Options);
}

static string FindRepoRoot(string start)
{
    var d = new DirectoryInfo(start);
    while (d is not null && d.Name != "umma") d = d.Parent!;
    return d?.FullName ?? start;
}
