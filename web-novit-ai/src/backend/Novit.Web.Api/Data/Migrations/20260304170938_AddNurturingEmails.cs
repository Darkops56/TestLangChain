using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Novit.Web.Api.Data.Migrations
{
    /// <inheritdoc />
    public partial class AddNurturingEmails : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "nurturing_emails",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    month_key = table.Column<string>(type: "character varying(7)", maxLength: 7, nullable: false),
                    body = table.Column<string>(type: "text", nullable: false),
                    subject = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: false),
                    scheduled_send_date = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    is_sent = table.Column<bool>(type: "boolean", nullable: false),
                    sent_at = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    created_at = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_nurturing_emails", x => x.id);
                });

            migrationBuilder.CreateIndex(
                name: "idx_nurturing_month_key",
                table: "nurturing_emails",
                column: "month_key",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "nurturing_emails");
        }
    }
}
