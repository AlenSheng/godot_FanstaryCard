using System.Diagnostics;
using System.IO.Compression;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Contracts.Bootstrap;
using FantasyCard.Contracts.Http;
using Google.Protobuf;
using Microsoft.AspNetCore.ResponseCompression;
using Npgsql;
using H = FantasyCard.Contracts.Http.V1;

// Diagnostic tool only. Every run uses a unique output directory and loopback endpoints.
if (args.Length < 3) throw new ArgumentException("codec|compression <bootstrap.json> <new-output-directory> OR diagnose <connection-file> <new-output-directory> <dotnet-exe> <server-dll> <server-project-directory>");
var output = Path.GetFullPath(args[2]);
if (Directory.Exists(output)) throw new InvalidOperationException("Output directory already exists; preserve prior runs by choosing a new name.");
Directory.CreateDirectory(output);
var jsonOptions = new JsonSerializerOptions(JsonSerializerDefaults.Web); jsonOptions.Converters.Add(new JsonStringEnumConverter());
var reportOptions = new JsonSerializerOptions { WriteIndented = true };
async Task Save(string file, object value) => await File.WriteAllTextAsync(Path.Combine(output,file),JsonSerializer.Serialize(value,reportOptions));
async Task Trace(object value) => await File.AppendAllTextAsync(Path.Combine(output,"requests.jsonl"),JsonSerializer.Serialize(value)+Environment.NewLine);
if(args[0] == "monitor")
{
    var settings=new NpgsqlConnectionStringBuilder((await File.ReadAllTextAsync(args[1])).Trim());
    if(settings.Host is not ("localhost" or "127.0.0.1" or "::1"))throw new InvalidOperationException("Loopback only.");
    await using var connection=new NpgsqlConnection(settings.ConnectionString);await connection.OpenAsync();
    for(int i=0;i<120;i++)
    {
        await using var query=new NpgsqlCommand("SELECT pid,state,coalesce(wait_event_type,''),coalesce(wait_event,''),coalesce(extract(epoch from now()-query_start),0)::double precision,left(query,240),array_to_string(pg_blocking_pids(pid),',') FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()",connection);
        await using(var reader=await query.ExecuteReaderAsync())
        {
            while(await reader.ReadAsync())await Trace(new{at=DateTimeOffset.UtcNow,pid=reader.GetInt32(0),state=reader.GetString(1),waitType=reader.GetString(2),wait=reader.GetString(3),queryAgeSeconds=reader.GetDouble(4),query=reader.GetString(5),blockedBy=reader.GetString(6)});
        }
        await Task.Delay(500);
    }
    return;
}
if(args[0] == "diagnose")
{
    var cs = new NpgsqlConnectionStringBuilder((await File.ReadAllTextAsync(args[1])).Trim());
    if(cs.Host is not ("localhost" or "127.0.0.1" or "::1")) throw new InvalidOperationException("Only isolated loopback PostgreSQL is allowed.");
    var schema = "pb_diagnostic_"+Guid.NewGuid().ToString("N");
    await using(var db = new NpgsqlConnection(cs.ConnectionString)) { await db.OpenAsync(); await using var command = new NpgsqlCommand($"CREATE SCHEMA {schema}",db); await command.ExecuteNonQueryAsync(); }
    cs.SearchPath=schema;
    var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();var port=((IPEndPoint)listener.LocalEndpoint).Port;listener.Stop();
    var start=new ProcessStartInfo(args[3]){WorkingDirectory=args[5],UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true,CreateNoWindow=true};
    start.ArgumentList.Add(Path.GetFullPath(args[4]));
    start.Environment["ASPNETCORE_ENVIRONMENT"]="Development";start.Environment["ASPNETCORE_URLS"]=$"http://127.0.0.1:{port}";
    start.Environment["ConnectionStrings__Postgres"]=cs.ConnectionString;start.Environment["Identity__EnableLocalAuth"]="true";
    start.Environment["ProtobufHttp__AllowLegacyJson"]="true";
    start.Environment["Logging__LogLevel__Microsoft.AspNetCore.Hosting.Diagnostics"]="Information";
    using var server=Process.Start(start)!;
    await using var stdout=File.CreateText(Path.Combine(output,"server.stdout.log"));
    await using var stderr=File.CreateText(Path.Combine(output,"server.stderr.log"));
    var outTask=server.StandardOutput.BaseStream.CopyToAsync(stdout.BaseStream);var errTask=server.StandardError.BaseStream.CopyToAsync(stderr.BaseStream);
    try
    {
        using var client=new HttpClient{BaseAddress=new Uri($"http://127.0.0.1:{port}"),Timeout=TimeSpan.FromSeconds(20)};
        for(int i=0;i<100;i++){if(server.HasExited)throw new InvalidOperationException("Server exited during readiness.");try{using var ready=await client.GetAsync("/health/live");if(ready.IsSuccessStatusCode)break;}catch(HttpRequestException){}await Task.Delay(100);}
        using var content=new ByteArrayContent(new H.LocalSignInRequest{DeviceId="pb-diagnostic-001",DisplayName="Diag"+Guid.NewGuid().ToString("N")[..10]}.ToByteArray());
        content.Headers.ContentType=new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        using var loginResponse=await client.PostAsync("/api/v1/auth/local",content);loginResponse.EnsureSuccessStatusCode();
        var login=H.LocalSignInResponse.Parser.ParseFrom(await loginResponse.Content.ReadAsByteArrayAsync());
        client.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",login.AccessToken);
        for(int i=0;i<120;i++)
        {
            var format=i%2==0?"protobuf":"json";
            using var request=new HttpRequestMessage(HttpMethod.Get,"/api/v1/bootstrap");request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue(format=="protobuf"?HttpProtocolRegistry.MediaType:"application/json"));
            var trace=$"diag-{i:D3}-{Guid.NewGuid():N}";request.Headers.Add("X-Trace-Id",trace);
            var startAt=DateTimeOffset.UtcNow;var watch=Stopwatch.StartNew();
            await Trace(new{phase="begin",i,format,trace,startAt});
            try
            {
                using var deadline=new CancellationTokenSource(TimeSpan.FromSeconds(20));
                using var response=await client.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,deadline.Token);var headersMs=watch.Elapsed.TotalMilliseconds;
                var body=await response.Content.ReadAsByteArrayAsync(deadline.Token);watch.Stop();
                await Trace(new{phase="complete",i,format,trace,status=(int)response.StatusCode,headersMs,elapsedMs=watch.Elapsed.TotalMilliseconds,bytes=body.Length});
                if(!response.IsSuccessStatusCode)throw new InvalidOperationException("Bootstrap non-success; see request trace.");
            }
            catch(Exception error)
            {
                await Trace(new{phase="failure",i,format,trace,elapsedMs=watch.Elapsed.TotalMilliseconds,error=error.GetType().FullName,message=error.Message,stack=error.StackTrace});
                throw;
            }
        }
        await Save("result.json",new{passed=true,requests=120,formats="alternating protobuf/json",timeoutSeconds=20,schema,serverPid=server.Id,runtime=Environment.Version.ToString()});
    }
    finally{if(!server.HasExited)server.Kill(true);await server.WaitForExitAsync();await Task.WhenAll(outTask,errTask);}
    return;
}
var source=await File.ReadAllBytesAsync(args[1]);var dto=JsonSerializer.Deserialize<BootstrapResponse>(source,jsonOptions)!;
var contract=HttpProtocolRegistry.Find("GET","/api/v1/bootstrap")!;
var pb=HttpDtoMapper.EncodeResponse(contract,dto);var json=JsonSerializer.SerializeToUtf8Bytes(dto,jsonOptions);
await File.WriteAllBytesAsync(Path.Combine(output,"sample.pb"),pb);
await Save("sample.json",new{sourceSha256=Convert.ToHexString(SHA256.HashData(source)),protobufSha256=Convert.ToHexString(SHA256.HashData(pb)),sourceBytes=source.Length,pbBytes=pb.Length,jsonBytes=json.Length,runtime=Environment.Version.ToString(),machine=Environment.MachineName});
if(args[0]=="codec")
{
    var results=new List<object>();
    void Measure(string name,Action run){for(int i=0;i<50;i++)run();GC.Collect();GC.WaitForPendingFinalizers();GC.Collect();var start=GC.GetAllocatedBytesForCurrentThread();var timer=Stopwatch.StartNew();for(int i=0;i<300;i++)run();timer.Stop();results.Add(new{name,iterations=300,microsecondsPerOperation=timer.Elapsed.TotalMicroseconds/300,allocatedBytesPerOperation=(GC.GetAllocatedBytesForCurrentThread()-start)/300});}
    Measure("protobuf encode DTO",()=>HttpDtoMapper.EncodeResponse(contract,dto));Measure("JSON encode DTO",()=>JsonSerializer.SerializeToUtf8Bytes(dto,jsonOptions));
    Measure("protobuf decode DTO",()=>HttpDtoMapper.ToDto(H.BootstrapResponse.Parser.ParseFrom(pb),typeof(BootstrapResponse)));Measure("JSON decode DTO",()=>JsonSerializer.Deserialize<BootstrapResponse>(json,jsonOptions));
    await Save("codec.json",results);return;
}
if(args[0]!="compression")throw new ArgumentException("Unknown mode");
var builder=WebApplication.CreateBuilder();builder.WebHost.UseUrls("http://127.0.0.1:0");builder.Logging.ClearProviders();
builder.Services.AddResponseCompression(o=>{o.Providers.Add<GzipCompressionProvider>();o.MimeTypes=new[]{"application/protobuf","application/json"};});
builder.Services.Configure<GzipCompressionProviderOptions>(o=>o.Level=CompressionLevel.Fastest);
await using var app=builder.Build();app.UseResponseCompression();
app.MapGet("/sample/{format}",(string format)=>Results.Bytes(format=="protobuf"?HttpDtoMapper.EncodeResponse(contract,dto):JsonSerializer.SerializeToUtf8Bytes(dto,jsonOptions),format=="protobuf"?"application/protobuf":"application/json"));
await app.StartAsync();using var handler=new HttpClientHandler{AutomaticDecompression=DecompressionMethods.None};using var http=new HttpClient(handler){BaseAddress=new Uri(app.Urls.Single()),Timeout=TimeSpan.FromSeconds(20)};
foreach(var format in new[]{"protobuf","json"})foreach(var gzip in new[]{false,true})
{
    for(int i=-10;i<100;i++)
    {
        using var request=new HttpRequestMessage(HttpMethod.Get,"/sample/"+format);if(gzip)request.Headers.AcceptEncoding.Add(new StringWithQualityHeaderValue("gzip"));
        var timer=Stopwatch.StartNew();using var response=await http.SendAsync(request);var body=await response.Content.ReadAsByteArrayAsync();timer.Stop();
        var compressed=response.Content.Headers.ContentEncoding.Contains("gzip");if(compressed!=gzip)throw new InvalidOperationException("Compression negotiation failed");
        byte[] decoded=body;
        if(compressed){using var stream=new GZipStream(new MemoryStream(body),CompressionMode.Decompress);using var destination=new MemoryStream();await stream.CopyToAsync(destination);decoded=destination.ToArray();}
        if(!decoded.AsSpan().SequenceEqual(format=="protobuf"?pb:json))throw new InvalidOperationException("HTTP body changed during compression transport");
        if(i>=0)await Trace(new{format,gzip,i,elapsedMs=timer.Elapsed.TotalMilliseconds,bytes=body.Length});
    }
}
await app.StopAsync();await Save("result.json",new{passed=true,requests=400,scope="loopback Kestrel captured Bootstrap DTO fixture; no DB/auth; response encoded per request; gzip Fastest; production unchanged"});
