import discord
from discord.ext import commands
from utils.logger import setup_logger

logger = setup_logger(__name__)

ALLOWED_ROLE_IDS = [1185158470958333953]

# Danh sách từ không được phép (viết thường, không phân biệt hoa/thường)
BANNED_WORDS = [
    # === Từ tục tĩu tiếng Việt ===
    "địt", "đĩ", "lồn", "cặc", "buồi", "chịch", "đéo", "đụ",
    "vãi lồn", "vl", "clm", "đmm", "đm", "đmcs", "đcm",
    "mẹ mày", "mẹ m", "má mày", "má m",
    "con chó", "thằng chó", "đồ chó", "súc vật",
    "ngu", "óc chó", "não cá vàng", "đần", "khùng", "điên",
    "mày chết đi", "chết đi", "tự tử",
    "thằng điên", "con điên", "thằng ngu", "con ngu",

    # === Phân biệt vùng miền / kỳ thị ===
    "bắc kỳ", 

    # === Spam / quảng cáo phổ biến ===
    "kiếm tiền online", "free robux", "click vào link","bro"
]

class Delete(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bỏ qua tin nhắn của bot
        if message.author.bot:
            return

        content_lower = message.content.lower()
        if any(word in content_lower for word in BANNED_WORDS):
            try:
                await message.delete()
                logger.info(
                    f"Đã xóa tin nhắn của {message.author} trong #{message.channel.name} "
                    f"vì chứa từ bị cấm (ID: {message.id})"
                )
            except discord.Forbidden:
                logger.error(f"Không có quyền xóa tin nhắn {message.id} trong #{message.channel.name}")
            except discord.NotFound:
                pass
            except Exception as e:
                logger.error(f"Lỗi khi xóa tin nhắn từ bị cấm {message.id}: {e}")

    @commands.command(name="delete")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def delete_user_messages(self, ctx: commands.Context, member: discord.Member, amount: int = 30):
        """
        Xóa tin nhắn của người dùng được đề cập
        
        Sử dụng: !delete @user [số lượng]
        Ví dụ: !delete @user 30
        """
        # Kiểm tra role của người dùng
        user_role_ids = [role.id for role in ctx.author.roles]
        has_required_role = any(role_id in ALLOWED_ROLE_IDS for role_id in user_role_ids)
        
        if not has_required_role:
            await ctx.send(f"❌ Bạn không có quyền sử dụng lệnh này! Cần một trong các role ID: {', '.join(map(str, ALLOWED_ROLE_IDS))}")
            logger.warning(f"{ctx.author} cố gắng dùng !delete nhưng không có role phù hợp")
            return
        
        if amount <= 0:
            await ctx.send("❌ Số lượng tin nhắn phải lớn hơn 0!")
            return
        
        if amount > 100:
            await ctx.send("❌ Chỉ có thể xóa tối đa 100 tin nhắn mỗi lần!")
            return
        
        try:
            # Gửi thông báo đang xử lý
            processing_msg = await ctx.send(f"🔍 Đang quét tất cả kênh để xóa tin nhắn của {member.mention}...")
            
            # Xóa tin nhắn lệnh
            try:
                await ctx.message.delete()
            except:
                pass
            
            # Thu thập tin nhắn của user từ tất cả các kênh
            user_messages = []
            checked = 0
            
            # Duyệt qua tất cả kênh text trong server
            for channel in ctx.guild.text_channels:
                try:
                    async for message in channel.history(limit=200):
                        checked += 1
                        if message.author.id == member.id:
                            user_messages.append(message)
                            if len(user_messages) >= 40:
                                break
                    
                    if len(user_messages) >= 40:
                        break
                except discord.Forbidden:
                    logger.warning(f"Không có quyền đọc lịch sử trong #{channel.name}")
                    continue
                except Exception as e:
                    logger.error(f"Lỗi khi quét kênh #{channel.name}: {e}")
                    continue
            
            # Sắp xếp theo thời gian (mới nhất trước)
            user_messages.sort(key=lambda m: m.created_at, reverse=True)
            
            # Chỉ lấy 40 tin nhắn gần nhất của user
            user_messages = user_messages[:40]
            
            # Xóa tin nhắn
            deleted = 0
            channels_affected = []
            
            for message in user_messages:
                if deleted >= amount:
                    break
                try:
                    await message.delete()
                    deleted += 1
                    if message.channel.name not in channels_affected:
                        channels_affected.append(message.channel.name)
                    logger.info(f"Đã xóa tin nhắn ID {message.id} của {member} trong #{message.channel.name}")
                except discord.errors.NotFound:
                    logger.warning(f"Tin nhắn {message.id} không tìm thấy")
                    continue
                except discord.errors.Forbidden:
                    logger.error(f"Không có quyền xóa tin nhắn {message.id}")
                    continue
                except Exception as e:
                    logger.error(f"Lỗi khi xóa tin nhắn {message.id}: {e}")
                    continue
            
            # Xóa thông báo đang xử lý
            try:
                await processing_msg.delete()
            except:
                pass
            
            # Gửi thông báo kết quả
            if deleted > 0:
                channels_info = f" trong {len(channels_affected)} kênh ({', '.join(['#' + ch for ch in channels_affected[:3]])}{'...' if len(channels_affected) > 3 else ''})"
                result_msg = await ctx.send(f"✅ Đã xóa **{deleted}** tin nhắn của {member.mention}{channels_info} (đã kiểm tra {checked} tin nhắn)")
                logger.info(f"{ctx.author} (roles: {user_role_ids}) đã xóa {deleted} tin nhắn của {member} trong các kênh: {channels_affected}")
            else:
                result_msg = await ctx.send(f"⚠️ Không tìm thấy tin nhắn nào của {member.mention} trong {checked} tin nhắn đã kiểm tra")
                logger.warning(f"{ctx.author} không tìm thấy tin nhắn của {member}")
            
            # Tự xóa sau 5 giây
            await result_msg.delete(delay=5)
            
        except discord.Forbidden as e:
            await ctx.send(f"❌ Bot không có quyền cần thiết! Cần: Manage Messages, Read Message History\nLỗi: {e}")
            logger.error(f"Forbidden error: {e}")
        except Exception as e:
            await ctx.send(f"❌ Có lỗi xảy ra: {str(e)}")
            logger.error(f"Lỗi trong lệnh delete: {e}", exc_info=True)

    @delete_user_messages.error
    async def delete_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ Bot không có quyền cần thiết! (Cần quyền: Manage Messages, Read Message History)")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Vui lòng đề cập người dùng cần xóa tin nhắn!\nSử dụng: `!delete @user [số lượng]`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Không tìm thấy người dùng hoặc số lượng không hợp lệ!")
        else:
            await ctx.send(f"❌ Có lỗi xảy ra: {str(error)}")
            logger.error(f"Lỗi trong delete command: {error}", exc_info=True)

async def setup(bot):
    await bot.add_cog(Delete(bot))
