using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace CmPlatform.Api.Data;

public class NovitDbContextFactory : IDesignTimeDbContextFactory<NovitDbContext>
{
    public NovitDbContext CreateDbContext(string[] args)
    {
        var connectionString = Environment.GetEnvironmentVariable("CONNECTION_STRING")
            ?? "Host=localhost;Database=cm_platform;Username=postgres;Password=postgres";

        var optionsBuilder = new DbContextOptionsBuilder<NovitDbContext>();
        optionsBuilder.UseNpgsql(connectionString);
        return new NovitDbContext(optionsBuilder.Options);
    }
}
