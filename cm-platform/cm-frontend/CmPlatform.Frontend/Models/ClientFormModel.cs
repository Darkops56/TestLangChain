using System.ComponentModel.DataAnnotations;

namespace CmPlatform.Frontend.Models;

public sealed class ClientFormModel
{
    public Guid? Id { get; set; }

    [Required(ErrorMessage = "El nombre es obligatorio")]
    [StringLength(100, ErrorMessage = "El nombre no puede superar los 100 caracteres")]
    public string Name { get; set; } = "";

    [Required(ErrorMessage = "El email es obligatorio")]
    [EmailAddress(ErrorMessage = "Email inválido")]
    [StringLength(200)]
    public string Email { get; set; } = "";

    [Phone(ErrorMessage = "Teléfono inválido")]
    [StringLength(50)]
    public string? Phone { get; set; }

    [StringLength(200)]
    public string? Company { get; set; }

    [StringLength(2000)]
    public string? Notes { get; set; }
}
